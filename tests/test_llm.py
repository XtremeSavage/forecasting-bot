import pytest
from pydantic import BaseModel
from bot.config import load_settings
from bot.llm import Llm, extract_json, LlmError, CostCeilingError


class FakeTransport:
    def __init__(self, replies=None, fail_openrouter=False):
        self.replies = list(replies or [])
        self.fail_openrouter = fail_openrouter
        self.calls = []

    async def openrouter(self, model, messages, temperature, max_tokens):
        self.calls.append(("openrouter", model))
        if self.fail_openrouter:
            raise RuntimeError("openrouter down")
        text = self.replies.pop(0) if self.replies else "ok"
        return {"text": text, "prompt_tokens": 100, "completion_tokens": 50, "cost": 0.0012}

    async def anthropic(self, model, messages, temperature, max_tokens):
        self.calls.append(("anthropic", model))
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


async def test_no_fallback_for_non_anthropic_model():
    s = load_settings("config.yaml")
    t = FakeTransport(fail_openrouter=True)
    llm = Llm(s, transport=t)
    with pytest.raises(LlmError):
        await llm.complete("hi", model="openai/gpt-5.4")


async def test_complete_json_retries_once_then_parses():
    s = load_settings("config.yaml")
    t = FakeTransport(replies=["garbage", '{"a": 3, "b": "y"}'])
    llm = Llm(s, transport=t)
    out, res = await llm.complete_json("p", model="openai/gpt-5.4", out_type=Out)
    assert out.a == 3 and len(t.calls) == 2


async def test_cost_ceiling_raises():
    s = load_settings("config.yaml")
    s.limits.per_call_usd = 0.001
    t = FakeTransport(replies=["x"])
    llm = Llm(s, transport=t)
    with pytest.raises(CostCeilingError):
        await llm.complete("hi", model="openai/gpt-5.4")
