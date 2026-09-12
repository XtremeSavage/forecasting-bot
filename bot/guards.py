from __future__ import annotations
import json
import time
from pathlib import Path
from bot.models import ForecastValue, MemberForecast, QuestionSummary


def consistency_ok(m: MemberForecast, tol: float = 0.05) -> bool:
    v, s = m.forecast, m.stated_number
    if s is None:
        return True
    if v.kind == "binary":
        return abs(v.probability - s) <= tol
    if v.kind == "multiple_choice":
        top = max(v.options.values())
        return abs(top - s) <= tol
    ps = v.percentiles
    lo, hi = ps.get(10, min(ps.values())), ps.get(90, max(ps.values()))
    return lo <= s <= hi


def validate_value(v: ForecastValue, q: QuestionSummary) -> list[str]:
    problems: list[str] = []
    if v.kind == "binary":
        if v.probability is None or not (0 < v.probability < 1):
            problems.append("binary probability out of (0,1)")
    elif v.kind == "multiple_choice":
        if v.options is None or set(v.options) != set(q.options or []):
            problems.append("option keys do not match question options")
        elif abs(sum(v.options.values()) - 1) > 0.02:
            problems.append("option probabilities do not sum to 1")
    else:
        if not v.percentiles:
            problems.append("no percentiles")
        else:
            vals = [v.percentiles[k] for k in sorted(v.percentiles)]
            if any(b <= a for a, b in zip(vals, vals[1:])):
                problems.append("percentiles not strictly increasing")
            if q.lower_bound is not None and q.open_lower is False and vals[0] < q.lower_bound:
                problems.append("value below closed lower bound")
            if q.upper_bound is not None and q.open_upper is False and vals[-1] > q.upper_bound:
                problems.append("value above closed upper bound")
    return problems


def drop_invalid_members(members: list[MemberForecast], q: QuestionSummary) -> list[MemberForecast]:
    survivors = []
    for m in members:
        probs = validate_value(m.forecast, q)
        if probs:
            m.dropped_reason = "; ".join(probs)
        elif not consistency_ok(m):
            m.dropped_reason = "stated number disagrees with JSON forecast"
        else:
            survivors.append(m)
    return survivors


def enough_members(survivors: list[MemberForecast], min_members: int) -> bool:
    return len(survivors) >= min_members


class Budget:
    def __init__(self, wall_clock_s: int, per_question_usd: float) -> None:
        self.start = time.monotonic()
        self.wall = wall_clock_s
        self.cap = per_question_usd

    def elapsed_fraction(self) -> float:
        return (time.monotonic() - self.start) / self.wall

    def spent_fraction(self, cost: float) -> float:
        return cost / self.cap

    def should_skip_da(self, cost: float, frac: float) -> bool:
        return self.elapsed_fraction() >= frac or self.spent_fraction(cost) >= frac

    def exhausted(self, cost: float) -> bool:
        return self.elapsed_fraction() >= 1.0 or cost > self.cap


def season_spent(runs_dir: str) -> float:
    total = 0.0
    for p in Path(runs_dir).glob("**/*.json"):
        try:
            total += float(json.loads(p.read_text(encoding="utf-8")).get("cost_usd", 0.0))
        except (json.JSONDecodeError, OSError):
            continue
    return total
