from __future__ import annotations
from bot.llm import Llm, LlmResult
from bot.config import Settings
from bot.models import BlindEstimate, Forensics, QuestionSummary
from bot.stages.common import CONVENTION, question_block, forecast_json_instructions, parse_forecast_json
from pydantic import BaseModel

SYSTEM = "You are a calibrated forecaster producing an outside-view estimate. You have NO news access; use only general knowledge and base rates."


class _Out(BaseModel):
    reference_class: str
    base_rate_reasoning: str
    forecast: dict


def build_prompt(q: QuestionSummary, description: str, criteria: str, forensics: Forensics, today: str) -> str:
    return f"""{question_block(q, description, criteria, "", today)}
{CONVENTION}
Resolution forensics summary: {forensics.resolution_statement}
Status quo outcome: {forensics.status_quo_outcome}

Produce a BLIND outside-view estimate without any current news:
1. Choose a reference class: what kind of event is this, and how often do such things happen in comparable windows? Be concrete about the class and its size.
2. Give the base rate and adjust only for structural features visible in the question itself (time remaining, how many things must go right, whether the status quo is sticky).
3. State the estimate.

{forecast_json_instructions(q, [5, 10, 20, 40, 60, 80, 90, 95])}
Wrap it so the JSON object has the keys "reference_class", "base_rate_reasoning", and "forecast" (the forecast object described above)."""


async def run(llm: Llm, settings: Settings, q: QuestionSummary, description: str, criteria: str, forensics: Forensics, today: str) -> tuple[BlindEstimate, LlmResult]:
    prompt = build_prompt(q, description, criteria, forensics, today)
    out, res = await llm.complete_json(prompt, settings.models.forecast_tier, _Out, temperature=0.3, system=SYSTEM)
    return BlindEstimate(reference_class=out.reference_class, base_rate_reasoning=out.base_rate_reasoning,
                         forecast=parse_forecast_json(out.forecast, q)), res
