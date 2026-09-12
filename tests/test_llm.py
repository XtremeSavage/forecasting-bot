import pytest
from pydantic import BaseModel
from bot.config import load_settings
from bot.llm import Llm, extract_json, LlmError, CostCeilingError


class FakeTransport:
    def __init__(self, replies=None, fail_openrouter=False, fail_anthropic=False):
        self.replies = list(replies or [])
        self.fail_openrouter = fail_openrouter
        self.fail_anthropic = fail_anthropic
        self.calls = []

    async def openrouter(self, model, messages, temperature, max_tokens):
        self.calls.append(("openrouter", model))
        if self.fail_openrouter:
            raise RuntimeError("openrouter down")
        text = self.replies.pop(0) if self.replies else "ok"
        return {"text": text, "prompt_tokens": 100, "completion_tokens": 50, "cost": 0.0012}

    async def anthropic(self, model, messages, temperature, max_tokens):
        self.calls.append(("anthropic", model))
        if self.fail_anthropic:
            raise RuntimeError("anthropic down")
        text = self.replies.pop(0) if self.replies else "ok"
        return {"text": text, "prompt_tokens": 100, "completion_tokens": 50, "cost": None}


class Out(BaseModel):
    a: int
    b: str


def test_extract_json_fenced_and_bare():
    assert extract_json('blah ```json\n{"a": 1}\n``` more') == {"a": 1}
    assert extract_json('prefix {"a": 2, "b": "x"} suffix') == {"a": 2, "b": "x"}
    with pytest.raises(LlmError):
        extract_json("no json here")
    nested = '```json\n{"items": [{"a": {"b": 1}}], "x": ""}\n```'
    assert extract_json(nested) == {"items": [{"a": {"b": 1}}], "x": ""}
    nested_trailing = nested + " some trailing prose with a stray } in it"
    assert extract_json(nested_trailing) == {"items": [{"a": {"b": 1}}], "x": ""}


async def test_complete_uses_openrouter_cost():
    s = load_settings("config.yaml")
    t = FakeTransport(replies=["hello"])
    llm = Llm(s, transport=t)
    r = await llm.complete("hi", model="openai/gpt-5.4")
    assert r.text == "hello" and r.cost_usd == 0.0012 and r.provider == "openrouter"


async def test_fallback_to_anthropic_when_openrouter_fails():
    s = load_settings("config.yaml")
    t = FakeTransport(replies=["from claude"], fail_openrouter=True)
    llm = Llm(s, transport=t)
    r = await llm.complete("hi", model="anthropic/claude-sonnet-4.6")
    assert r.provider == "anthropic" and r.text == "from claude"
    assert r.cost_usd == pytest.approx(100 * 3 / 1e6 + 50 * 15 / 1e6)
    assert llm.fallback_used is True


async def test_generic_fallback_to_anthropic_model():
    # OpenRouter is the single point of failure for every model, not just anthropic/*.
    # A non-anthropic model has no direct route, so it falls back to the configured
    # Anthropic model rather than losing the call.
    s = load_settings("config.yaml")
    t = FakeTransport(replies=["from claude"], fail_openrouter=True)
    llm = Llm(s, transport=t)
    r = await llm.complete("hi", model="openai/gpt-5.4")
    assert r.provider == "anthropic" and r.text == "from claude"
    assert r.model == s.models.anthropic_fallback == "claude-sonnet-4-6"
    assert r.cost_usd == pytest.approx(100 * 3 / 1e6 + 50 * 15 / 1e6)  # ANTHROPIC_PRICES entry
    assert llm.fallback_used is True
    assert t.calls == [("openrouter", "openai/gpt-5.4"), ("anthropic", "claude-sonnet-4-6")]


async def test_generic_fallback_raises_when_anthropic_also_fails():
    s = load_settings("config.yaml")
    t = FakeTransport(fail_openrouter=True, fail_anthropic=True)
    llm = Llm(s, transport=t)
    with pytest.raises(LlmError):
        await llm.complete("hi", model="openai/gpt-5.4")


async def test_fallback_raises_llm_error_when_anthropic_also_fails():
    s = load_settings("config.yaml")
    t = FakeTransport(fail_openrouter=True, fail_anthropic=True)
    llm = Llm(s, transport=t)
    with pytest.raises(LlmError):
        await llm.complete("hi", model="anthropic/claude-sonnet-4.6")
    assert llm.fallback_used is True


async def test_complete_json_retries_once_then_parses():
    s = load_settings("config.yaml")
    t = FakeTransport(replies=["garbage", '{"a": 3, "b": "y"}'])
    llm = Llm(s, transport=t)
    out, res = await llm.complete_json("p", model="openai/gpt-5.4", out_type=Out)
    assert out.a == 3 and len(t.calls) == 2


async def test_precall_estimate_ceiling_raises():
    s = load_settings("config.yaml")
    s.limits.per_call_usd = 0.001
    t = FakeTransport(replies=["x"])
    llm = Llm(s, transport=t)
    with pytest.raises(CostCeilingError):
        await llm.complete("hi", model="openai/gpt-5.4")
    assert t.calls == []


async def test_postcall_cost_ceiling_raises():
    s = load_settings("config.yaml")
    s.limits.per_call_usd = 0.001
    t = FakeTransport(replies=["x"])
    llm = Llm(s, transport=t)
    with pytest.raises(CostCeilingError):
        await llm.complete("hi", model="openai/gpt-5.4", max_tokens=10)
    assert len(t.calls) == 1
