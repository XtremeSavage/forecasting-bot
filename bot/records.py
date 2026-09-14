from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from forecasting_tools import MetaculusQuestion, MultipleChoiceQuestion, NumericQuestion, DateQuestion
from bot.models import ForecastRecord, QuestionSummary


def question_summary(q: MetaculusQuestion) -> QuestionSummary:
    # `get_question_type()` is an instance method that returns the api type name
    # string directly (e.g. "binary"), asserting it matches `type(q).get_api_type_name()`.
    kind = q.get_question_type()
    lo = hi = zp = None
    open_lo = open_hi = None
    cdf_size = None
    if isinstance(q, DateQuestion):
        lo, hi = q.lower_bound.timestamp(), q.upper_bound.timestamp()
        open_lo, open_hi, zp, cdf_size = q.open_lower_bound, q.open_upper_bound, q.zero_point, q.cdf_size
    elif isinstance(q, NumericQuestion):
        lo, hi = q.lower_bound, q.upper_bound
        open_lo, open_hi, zp, cdf_size = q.open_lower_bound, q.open_upper_bound, q.zero_point, q.cdf_size
    return QuestionSummary(
        post_id=q.id_of_post, question_id=q.id_of_question, url=q.page_url or "", title=q.question_text, kind=kind,
        close_time=q.close_time.isoformat() if q.close_time else None,
        options=q.options if isinstance(q, MultipleChoiceQuestion) else None,
        lower_bound=lo, upper_bound=hi, open_lower=open_lo, open_upper=open_hi, cdf_size=cdf_size, zero_point=zp,
        unit=q.unit_of_measure,
    )


def write(rec: ForecastRecord, runs_dir: str = "runs") -> str:
    ts = datetime.fromisoformat(rec.run_ts)
    day = ts.astimezone(timezone.utc).strftime("%Y-%m-%d")
    compact = ts.astimezone(timezone.utc).strftime("%H%M%S")
    d = Path(runs_dir) / day
    d.mkdir(parents=True, exist_ok=True)
    # A post can be a question group with several subquestions, and concurrent tasks
    # stamp run_ts in the same second, so the name carries both ids and never overwrites.
    stem = f"{rec.question.post_id}_{rec.question.question_id}_{compact}"
    p = d / f"{stem}.json"
    n = 1
    while p.exists():
        n += 1
        p = d / f"{stem}_{n}.json"
    p.write_text(rec.model_dump_json(indent=1), encoding="utf-8")
    return str(p)


def already_forecasted_locally(post_id: int, question_id: int | None, runs_dir: str = "runs") -> bool:
    """True if a *published* record exists for this exact subquestion.

    Identity is the JSON body's question.question_id, not the filename: records written
    before 2026-09-14 are named {post_id}_{HHMMSS}.json and would otherwise make every
    sibling in a question group look already forecast (live: post 43322, subquestions
    43323 and 43324).
    """
    for p in Path(runs_dir).glob(f"**/{post_id}_*.json"):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not r.get("published"):
            continue
        rq = (r.get("question") or {}).get("question_id")
        if question_id is None or rq is None or rq == question_id:
            return True
    return False
