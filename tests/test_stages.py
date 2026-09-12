import json
from pathlib import Path
from bot.config import load_settings
from bot.models import QuestionSummary, Forensics, BlindEstimate, EvidenceTable, Evidence, ForecastValue, ResearchBundle, RawSource
from bot.stages import forensics, base_rate, evidence, forecast, devils_advocate
from bot.stages.common import parse_forecast_json

FIX = Path("tests/fixtures")


def _q(kind="binary"):
    return QuestionSummary(post_id=1, question_id=1, url="u", title="Will X happen before 2026-10-01?", kind=kind, close_time="2026-09-30T00:00:00+00:00",
                           options=["A", "B"] if kind == "multiple_choice" else None, lower_bound=0.0 if kind == "numeric" else None,
                           upper_bound=100.0 if kind == "numeric" else None, open_lower=False, open_upper=False, cdf_size=201, zero_point=None, unit="count")


class FakeLlm:
    def __init__(self, texts):
        self.texts = list(texts)
        self.prompts = []

    async def complete(self, prompt, model, temperature=0.5, system=None, max_tokens=4000):
        from bot.llm import LlmResult
        self.prompts.append(prompt)
        return LlmResult(text=self.texts.pop(0), model=model, cost_usd=0.01, prompt_tokens=1, completion_tokens=1, provider="openrouter")

    async def complete_json(self, prompt, model, out_type, temperature=0.5, retries=1, system=None, max_tokens=4000):
        from bot.llm import extract_json
        res = await self.complete(prompt, model, temperature, system, max_tokens)
        return out_type.model_validate(extract_json(res.text)), res


def test_forensics_prompt_and_parse():
    s = load_settings("config.yaml")
    text = "analysis...\n```json\n" + (FIX / "forensics_binary.json").read_text() + "\n```"
    llm = FakeLlm([text])
    import asyncio
    f, res = asyncio.run(forensics.run(llm, s, _q(), "desc", "crit", "fine", "2026-09-12"))
    assert isinstance(f, Forensics) and f.status_quo_outcome == "No" and len(f.search_queries) == 2
    assert "NOT yet happened" in llm.prompts[0] and "Resolution criteria" in llm.prompts[0]


def test_forecast_parse_binary_with_stated_number():
    v, stated = forecast.parse((FIX / "forecast_binary.txt").read_text(), _q())
    assert v.probability == 0.18 and stated == 0.18


def test_forecast_parse_numeric():
    text = 'reasoning\nFINAL: 50\n```json\n{"percentiles": {"10": 20, "50": 50, "90": 80}}\n```'
    v, stated = forecast.parse(text, _q("numeric"))
    assert v.percentiles == {10: 20.0, 50: 50.0, 90: 80.0} and stated == 50.0


def test_forecast_prompt_includes_blind_and_evidence():
    s = load_settings("config.yaml")
    f = Forensics.model_validate(json.loads((FIX / "forensics_binary.json").read_text()))
    b = BlindEstimate(reference_class="rc", base_rate_reasoning="br", forecast=ForecastValue(kind="binary", probability=0.2))
    e = EvidenceTable(items=[Evidence(claim="c", source="s", reliability="B", credibility=2, supports="Yes")])
    p = forecast.build_prompt(_q(), "d", "c", "f", f, b, e, "2026-09-12", s.forecast.numeric_percentiles)
    assert "reference class" in p.lower() and "B2" in p and "status quo" in p.lower() and "FINAL:" in p


def test_evidence_prompt_lists_sources():
    f = Forensics.model_validate(json.loads((FIX / "forensics_binary.json").read_text()))
    bundle = ResearchBundle(sources=[RawSource(provider="asknews", url="http://a", title="T", published="2026-09-10", text="body")])
    p = evidence.build_prompt(_q(), f, bundle, "2026-09-12")
    assert "http://a" in p and "reliability" in p.lower()


def test_da_prompts():
    f = Forensics.model_validate(json.loads((FIX / "forensics_binary.json").read_text()))
    e = EvidenceTable()
    agg = ForecastValue(kind="binary", probability=0.18)
    assert "0.18" in devils_advocate.critique_prompt(_q(), f, e, agg)
    assert "critique" in devils_advocate.revise_prompt(_q(), agg, "the critique text", [10, 50, 90]).lower()
