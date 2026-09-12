from __future__ import annotations
import re
from bot.config import Member, Settings
from bot.llm import Llm, extract_json
from bot.models import BlindEstimate, EvidenceTable, Forensics, ForecastValue, MemberForecast, QuestionSummary
from bot.stages.common import CONVENTION, question_block, forecast_json_instructions, parse_forecast_json

SYSTEM = "You are a superforecaster applying analysis of competing hypotheses. You are calibrated: you avoid extreme probabilities unless the evidence is decisive, and you give extra weight to the status quo."


def _fmt_value(v: ForecastValue) -> str:
    if v.kind == "binary":
        return f"P(Yes) = {v.probability:.2f}"
    if v.kind == "multiple_choice":
        return ", ".join(f"{k}: {p:.2f}" for k, p in v.options.items())
    return ", ".join(f"p{k}={val}" for k, val in sorted(v.percentiles.items()))


def build_prompt(q, description, criteria, fine_print, forensics: Forensics, blind: BlindEstimate | None,
                 evidence: EvidenceTable | None, today: str, percentiles: list[int]) -> str:
    blind_txt = "(blind base rate stage disabled)"
    if blind:
        blind_txt = f"Reference class: {blind.reference_class}\nBase-rate reasoning: {blind.base_rate_reasoning}\nBlind estimate: {_fmt_value(blind.forecast)}"
    ev_txt = "(evidence table stage disabled)"
    if evidence:
        rows = [f"E{i} [{e.reliability}{e.credibility}] ({e.date or 'n/d'}) supports {e.supports}: {e.claim} — {e.source}" for i, e in enumerate(evidence.items, 1)]
        ev_txt = "\n".join(rows) or "(no evidence extracted)"
        if evidence.already_resolved_signal:
            ev_txt += f"\nALREADY-RESOLVED SIGNAL: {evidence.already_resolved_signal}"
    return f"""{question_block(q, description, criteria, fine_print, today)}
{CONVENTION}

RESOLUTION FORENSICS
{forensics.resolution_statement}
Status quo outcome: {forensics.status_quo_outcome}
Traps: {forensics.traps}
Does not count: {forensics.things_that_do_not_count}

OUTSIDE VIEW (blind)
{blind_txt}

EVIDENCE TABLE (source reliability A-F, claim credibility 1-6)
{ev_txt}

Apply analysis of competing hypotheses:
1. List the hypotheses. H0 is the status quo outcome. Others are the alternatives (each option, or higher/lower ranges).
2. For each evidence item, say which hypotheses it is consistent with and which it contradicts. Weight by grade: A1-B2 evidence dominates; D-F or 4-6 barely moves you.
3. State what must change between today and close for a non-status-quo outcome, and how likely that is in the time left.
4. Start from the blind base rate and update on the evidence. Say how far you moved and why.
5. Give the forecast. Do not exceed 0.95 or go below 0.05 unless A1/A2 evidence makes the outcome near-certain.

Write one line "FINAL: <number>" giving the headline number (the Yes probability, the top option's probability, or your median), then
{forecast_json_instructions(q, percentiles)}"""


def parse(text: str, q: QuestionSummary) -> tuple[ForecastValue, float | None]:
    value = parse_forecast_json(extract_json(text), q)
    m = re.search(r"FINAL:\s*([-+]?\d[\d,]*\.?\d*)\s*(%?)", text)
    stated = None
    if m:
        stated = float(m.group(1).replace(",", ""))
        if m.group(2) == "%" or (q.kind in ("binary", "multiple_choice") and stated > 1):
            stated = stated / 100
    return value, stated


async def run_member(llm: Llm, settings: Settings, member: Member, q, description, criteria, fine_print, forensics, blind, evidence, today) -> MemberForecast:
    prompt = build_prompt(q, description, criteria, fine_print, forensics, blind, evidence, today, settings.forecast.numeric_percentiles)
    res = await llm.complete(prompt, member.model, temperature=member.temperature, system=SYSTEM, max_tokens=5000)
    try:
        value, stated = parse(res.text, q)
    except Exception as e:  # noqa: BLE001
        return MemberForecast(name=member.name, model=res.model, forecast=ForecastValue(kind=q.kind), reasoning=res.text,
                              stated_number=None, cost_usd=res.cost_usd, dropped_reason=f"parse failure: {e}")
    return MemberForecast(name=member.name, model=res.model, forecast=value, reasoning=res.text, stated_number=stated, cost_usd=res.cost_usd)
