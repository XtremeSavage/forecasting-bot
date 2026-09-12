import json
from pathlib import Path
from forecasting_tools import BinaryQuestion
from bot.config import load_settings
from bot import pipeline

FOR = '```json\n{"resolution_statement": "r", "status_quo_outcome": "No", "search_queries": ["q"]}\n```'
BLIND = '```json\n{"reference_class": "rc", "base_rate_reasoning": "br", "forecast": {"probability": 0.2}}\n```'
EVID = '```json\n{"items": [], "already_resolved_signal": ""}\n```'


def member(p):
    return f'reasoning\nFINAL: {p}\n```json\n{{"probability": {p}}}\n```'


CRIT = "critique text"
REV = '```json\n{"probability": 0.9}\n```'


class FakeLlm:
    def __init__(self, texts):
        self.texts = list(texts); self.total_cost_usd = 0.0; self.fallback_used = False

    async def complete(self, prompt, model, temperature=0.5, system=None, max_tokens=4000):
        from bot.llm import LlmResult
        self.total_cost_usd += 0.01
        return LlmResult(text=self.texts.pop(0), model=model, cost_usd=0.01, prompt_tokens=1, completion_tokens=1, provider="openrouter")

    async def complete_json(self, prompt, model, out_type, temperature=0.5, retries=1, system=None, max_tokens=4000):
        from bot.llm import extract_json
        res = await self.complete(prompt, model, temperature, system, max_tokens)
        return out_type.model_validate(extract_json(res.text)), res


class FakePublisher:
    def __init__(self, open_=True):
        self.open_ = open_; self.published = []

    def is_open(self, post_id):
        return self.open_

    def publish(self, q, value, comment):
        self.published.append((q.post_id, value, comment))


def _bq():
    return BinaryQuestion(question_text="Will X?", id_of_post=5, id_of_question=6, page_url="https://m/5",
                          background_info="bg", resolution_criteria="crit https://src.example/x", fine_print="fp")


async def test_full_binary_run_with_bounded_da(tmp_path, monkeypatch):
    s = load_settings("config.yaml")
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    texts = [FOR, BLIND, EVID, member(0.2), member(0.3), member(0.25), member(0.22), CRIT, REV]
    llm = FakeLlm(texts)
    pub = FakePublisher()
    rec = await pipeline.forecast_question(_bq(), s, llm, pub, "2026-09-12", runs_dir=str(tmp_path))
    assert rec.published and len(pub.published) == 1
    pre = rec.aggregate.pre_da.probability
    assert 0.2 <= pre <= 0.3
    # DA wanted 0.9 but the move is bounded to 0.5 logits
    assert rec.final.probability < 0.45 and rec.final.probability > pre
    assert rec.error is None and rec.cost_usd > 0
    assert list(Path(tmp_path).glob("**/5_*.json"))


async def test_skip_when_too_few_members(tmp_path):
    s = load_settings("config.yaml")
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    s.models.members = s.models.members[:2]
    texts = [FOR, BLIND, EVID, member(0.2), "no json at all"]
    rec = await pipeline.forecast_question(_bq(), s, FakeLlm(texts), FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    assert not rec.published and "SKIP_MIN_MEMBERS" in rec.guards_fired


async def test_publish_gate_closed(tmp_path):
    s = load_settings("config.yaml")
    s.stages.devils_advocate = False
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    texts = [FOR, BLIND, EVID, member(0.2), member(0.3), member(0.25), member(0.22)]
    rec = await pipeline.forecast_question(_bq(), s, FakeLlm(texts), FakePublisher(open_=False), "2026-09-12", runs_dir=str(tmp_path))
    assert not rec.published and "PUBLISH_SKIPPED_CLOSED" in rec.guards_fired


async def test_dry_run_writes_record_without_publishing(tmp_path):
    s = load_settings("config.yaml")
    s.stages.devils_advocate = False
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    texts = [FOR, BLIND, EVID, member(0.2), member(0.3), member(0.25), member(0.22)]
    rec = await pipeline.forecast_question(_bq(), s, FakeLlm(texts), None, "2026-09-12", runs_dir=str(tmp_path))
    assert not rec.published and rec.final is not None and rec.comment
