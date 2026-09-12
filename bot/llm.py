from __future__ import annotations
import json
import os
import re
from typing import Literal, Protocol, TypeVar
from pydantic import BaseModel, ValidationError
from bot.config import Settings

T = TypeVar("T", bound=BaseModel)

ANTHROPIC_PRICES = {  # USD per million tokens (input, output)
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
}
OPENROUTER_EST_PRICES = {  # used only for the pre-call estimate
    "openai/gpt-5.4": (2.5, 15.0),
    "openai/gpt-5.4-mini": (0.75, 4.5),
    "openai/gpt-5.4-mini:online": (0.75, 4.5),
    "anthropic/claude-sonnet-4.6": (3.0, 15.0),
    "x-ai/grok-4.6": (2.0, 6.0),
}


class LlmError(Exception):
    pass


class CostCeilingError(LlmError):
    pass


class LlmResult(BaseModel):
    text: str
    model: str
    cost_usd: float
    prompt_tokens: int
    completion_tokens: int
    provider: Literal["openrouter", "anthropic"]


class Transport(Protocol):
    async def openrouter(self, model: str, messages: list[dict], temperature: float, max_tokens: int) -> dict: ...
    async def anthropic(self, model: str, messages: list[dict], temperature: float, max_tokens: int) -> dict: ...


class HttpTransport:
    """Real transport. OpenRouter via the openai SDK; Anthropic via the anthropic SDK."""

    def __init__(self) -> None:
        from openai import AsyncOpenAI
        # The installed openai SDK raises at construction time if api_key is None
        # (it normally falls back to OPENAI_API_KEY, which we don't set for OpenRouter).
        # Fall back to a placeholder so import/construction never fails when the
        # OpenRouter key just hasn't been configured yet; real calls will then fail
        # with an auth error instead, which is the correct behavior.
        self._or = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY") or "missing",
            timeout=180,
        )
        self._anthropic = None

    async def openrouter(self, model, messages, temperature, max_tokens):
        resp = await self._or.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens,
            extra_body={"usage": {"include": True}},
        )
        usage = resp.usage
        cost = getattr(usage, "cost", None)
        if cost is None and hasattr(usage, "model_extra"):
            cost = (usage.model_extra or {}).get("cost")
        return {
            "text": resp.choices[0].message.content or "",
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "cost": float(cost) if cost is not None else None,
        }

    async def anthropic(self, model, messages, temperature, max_tokens):
        if self._anthropic is None:
            from anthropic import AsyncAnthropic
            self._anthropic = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), timeout=180)
        system = "\n".join(m["content"] for m in messages if m["role"] == "system") or None
        user_msgs = [m for m in messages if m["role"] != "system"]
        # NOTE: the installed anthropic SDK (1.5.0) has no `temperature` keyword on
        # Messages.create (its MessageCreateParamsBase TypedDict doesn't define one).
        # The Messages API itself still accepts a top-level "temperature" field, so we
        # pass it through extra_body rather than changing the Transport protocol.
        kwargs = {
            "model": model,
            "messages": user_msgs,
            "max_tokens": max_tokens,
            "extra_body": {"temperature": temperature},
        }
        if system:
            kwargs["system"] = system
        resp = await self._anthropic.messages.create(**kwargs)
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        return {"text": text, "prompt_tokens": resp.usage.input_tokens, "completion_tokens": resp.usage.output_tokens, "cost": None}


def extract_json(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidates = [m.group(1).strip()] if m else []
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    raise LlmError("no JSON object found in model output")


class Llm:
    def __init__(self, settings: Settings, transport: Transport | None = None) -> None:
        self.s = settings
        self.t = transport or HttpTransport()
        self.fallback_used = False
        self.total_cost_usd = 0.0

    def _anthropic_direct_name(self, openrouter_model: str) -> str | None:
        if not openrouter_model.startswith("anthropic/"):
            return None
        return openrouter_model.split("/", 1)[1].replace(".", "-")  # claude-sonnet-4.6 -> claude-sonnet-4-6

    def _estimate(self, prompt: str, model: str, max_tokens: int) -> float:
        inp, out = OPENROUTER_EST_PRICES.get(model, (5.0, 25.0))
        return (len(prompt) / 4) * inp / 1e6 + max_tokens * out / 1e6

    async def complete(self, prompt: str, model: str, temperature: float = 0.5, system: str | None = None, max_tokens: int = 4000) -> LlmResult:
        if self._estimate(prompt, model, max_tokens) > 2 * self.s.limits.per_call_usd:
            raise CostCeilingError(f"pre-call estimate exceeds 2x per-call ceiling for {model}")
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        try:
            raw = await self.t.openrouter(model, messages, temperature, max_tokens)
            provider, used_model = "openrouter", model
        except Exception as e:  # noqa: BLE001
            direct = self._anthropic_direct_name(model)
            if direct is None:
                raise LlmError(f"openrouter call failed for {model}: {e}") from e
            self.fallback_used = True
            try:
                raw = await self.t.anthropic(direct, messages, temperature, max_tokens)
            except Exception as e2:  # noqa: BLE001
                raise LlmError(f"openrouter and anthropic fallback both failed for {model}: {e}; {e2}") from e2
            provider, used_model = "anthropic", direct
        cost = raw.get("cost")
        if cost is None:
            inp, out = ANTHROPIC_PRICES.get(used_model, (5.0, 25.0))
            cost = raw["prompt_tokens"] * inp / 1e6 + raw["completion_tokens"] * out / 1e6
        res = LlmResult(text=raw["text"], model=used_model, cost_usd=float(cost),
                        prompt_tokens=raw["prompt_tokens"], completion_tokens=raw["completion_tokens"], provider=provider)
        self.total_cost_usd += res.cost_usd
        if res.cost_usd > self.s.limits.per_call_usd:
            raise CostCeilingError(f"call cost {res.cost_usd:.4f} exceeded per-call ceiling")
        return res

    async def complete_json(self, prompt: str, model: str, out_type: type[T], temperature: float = 0.5, retries: int = 1, system: str | None = None, max_tokens: int = 4000) -> tuple[T, LlmResult]:
        last_err: Exception | None = None
        total_cost = 0.0
        for attempt in range(retries + 1):
            res = await self.complete(prompt, model, temperature, system, max_tokens)
            total_cost += res.cost_usd
            try:
                obj = out_type.model_validate(extract_json(res.text))
                res.cost_usd = total_cost
                return obj, res
            except (LlmError, ValidationError) as e:
                last_err = e
                prompt = prompt + "\n\nYour previous reply did not contain a valid JSON object matching the schema. Reply again with ONLY the JSON object."
        raise LlmError(f"could not parse JSON after {retries + 1} attempts: {last_err}")
