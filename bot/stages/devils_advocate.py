from __future__ import annotations
from bot.config import Settings
from bot.llm import Llm, extract_json
from bot.models import EvidenceTable, Forensics, ForecastValue, QuestionSummary
from bot.stages.common import forecast_json_instructions, parse_forecast_json
from bot.stages.forecast import _fmt_value

CRITIC_SYSTEM = "You are the devil's advocate on an analytic red team. Your job is to find the strongest case that the team's forecast is wrong."
JUDGE_SYSTEM = "You are the senior analyst adjudicating between a forecast and a red-team critique. Move only as far as the critique's evidence justifies."


def critique_prompt(q: QuestionSummary, forensics: Forensics, evidence: EvidenceTable, aggregate: ForecastValue) -> str:
    rows = "\n".join(f"E{i} [{e.reliability}{e.credibility}] supports {e.supports}: {e.claim}" for i, e in enumerate(evidence.items, 1)) or "(none)"
    return f"""Question: {q.title}
Resolution: {forensics.resolution_statement}
Team forecast: {_fmt_value(aggregate)}
Evidence used:
{rows}

Argue the strongest case that this forecast is wrong in DIRECTION or MAGNITUDE. Consider: a misread resolution criterion, an already-resolved signal, over-weighting low-grade evidence, ignoring the base rate, ignoring time remaining, or an overlooked mechanism. Be specific and cite the evidence ids. End with one sentence: which direction the forecast should move, and roughly how much, or 'no change' if the critique is weak."""


def revise_prompt(q: QuestionSummary, aggregate: ForecastValue, critique: str, percentiles: list[int]) -> str:
    return f"""Question: {q.title}
Current forecast: {_fmt_value(aggregate)}

Red-team critique:
{critique}

Decide whether the critique justifies a change. Small moves are normal; large moves need decisive evidence named in the critique. Explain in three sentences, then
{forecast_json_instructions(q, percentiles)}"""


async def run(llm: Llm, settings: Settings, q: QuestionSummary, forensics: Forensics, evidence: EvidenceTable, aggregate: ForecastValue, today: str) -> tuple[ForecastValue, str, float]:
    c = await llm.complete(critique_prompt(q, forensics, evidence, aggregate), settings.models.forecast_tier, temperature=0.6, system=CRITIC_SYSTEM, max_tokens=2500)
    r = await llm.complete(revise_prompt(q, aggregate, c.text, settings.forecast.numeric_percentiles), settings.models.forecast_tier, temperature=0.2, system=JUDGE_SYSTEM, max_tokens=2500)
    revised = parse_forecast_json(extract_json(r.text), q)
    return revised, c.text, c.cost_usd + r.cost_usd
