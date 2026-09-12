from __future__ import annotations
from bot.models import ForecastValue, QuestionSummary

CONVENTION = (
    "Metaculus convention: assume the event described has NOT yet happened unless the evidence you are "
    "given explicitly shows that it has. 'Before <date>' questions are forward-looking from today. "
    "'As of <date>' questions are snapshots at that date. Read the resolution criteria literally."
)


def question_block(q: QuestionSummary, description: str, criteria: str, fine_print: str, today: str) -> str:
    bounds = ""
    if q.kind in ("numeric", "discrete", "date"):
        bounds = (f"\nRange: lower bound {q.lower_bound} ({'open' if q.open_lower else 'closed'}), "
                  f"upper bound {q.upper_bound} ({'open' if q.open_upper else 'closed'}). Units: {q.unit or 'not stated'}.")
    opts = f"\nOptions: {q.options}" if q.options else ""
    return (f"Today is {today}.\nQuestion type: {q.kind}\nTitle: {q.title}{opts}{bounds}\n"
            f"Close time: {q.close_time}\n\nBackground:\n{description}\n\nResolution criteria:\n{criteria}\n\nFine print:\n{fine_print}\n")


def forecast_json_instructions(q: QuestionSummary, percentiles: list[int]) -> str:
    if q.kind == "binary":
        return 'Finish with a fenced JSON block exactly like: ```json\n{"probability": 0.23}\n```'
    if q.kind == "multiple_choice":
        return ('Finish with a fenced JSON block mapping EVERY option name verbatim to a probability that sums to 1, exactly like: '
                '```json\n{"options": {"Option A": 0.6, "Option B": 0.4}}\n```')
    keys = ", ".join(f'"{p}": <value>' for p in percentiles)
    return (f"Finish with a fenced JSON block giving strictly increasing values at these percentiles, in the question's units, "
            f"never scientific notation: ```json\n{{\"percentiles\": {{{keys}}}}}\n```")


def parse_forecast_json(d: dict, q: QuestionSummary) -> ForecastValue:
    if q.kind == "binary":
        return ForecastValue(kind="binary", probability=float(d["probability"]))
    if q.kind == "multiple_choice":
        return ForecastValue(kind="multiple_choice", options={k: float(v) for k, v in d["options"].items()})
    return ForecastValue(kind=q.kind, percentiles={int(k): float(v) for k, v in d["percentiles"].items()})
