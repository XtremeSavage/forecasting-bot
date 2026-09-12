from __future__ import annotations
from bot.models import ForecastRecord, ForecastValue


def _fmt(v: ForecastValue | None) -> str:
    if v is None:
        return "n/a"
    if v.kind == "binary":
        return f"{v.probability:.2f}"
    if v.kind == "multiple_choice":
        return "; ".join(f"{k}: {p:.2f}" for k, p in v.options.items())
    return "; ".join(f"p{k}={val:g}" for k, val in sorted(v.percentiles.items()))


def build(rec: ForecastRecord, max_chars: int) -> str:
    head_parts = ["**Resolution forensics.** " + (rec.forensics.resolution_statement if rec.forensics else "stage off")]
    if rec.forensics:
        head_parts.append(f"Status quo: {rec.forensics.status_quo_outcome}. Traps: {'; '.join(rec.forensics.traps[:3]) or 'none noted'}.")
    if rec.blind:
        head_parts.append(f"**Blind base rate.** {rec.blind.reference_class}. Estimate {_fmt(rec.blind.forecast)}.")
    if rec.evidence and rec.evidence.items:
        top = sorted(rec.evidence.items, key=lambda e: (e.reliability, e.credibility))[:3]
        head_parts.append("**Key evidence.** " + " | ".join(f"[{e.reliability}{e.credibility}] {e.claim} ({e.source})" for e in top))
    if rec.aggregate:
        names = ", ".join(m.name for m in rec.members if m.dropped_reason is None)
        head_parts.append(f"**ACH ensemble** ({names}): {_fmt(rec.aggregate.pre_da)} via {rec.aggregate.method}.")
        if rec.aggregate.post_da is not None:
            head_parts.append(f"**Devil's advocate** moved it to {_fmt(rec.aggregate.post_da)}.")

    tail_parts = [f"**Final:** {_fmt(rec.final)}"]
    flags = ",".join(k for k, v in rec.flags.items() if v)
    tail_parts.append(f"_bot=XtremeSavageForecast stages={flags} cost=${rec.cost_usd:.2f}_")

    tail = "\n\n".join(tail_parts)
    head = "\n\n".join(head_parts)
    marker = "\n\n[truncated]"
    if len(tail) >= max_chars:
        # No room for any analysis at all: the forecast itself is what has to survive.
        return tail[:max_chars]
    head_budget = max_chars - len(tail) - 2  # 2 for the blank line between head and tail
    if len(head) > head_budget:
        # A tiny max_chars can leave no room even for the marker, hence the max(..., 0)
        # and the final clamp: the tail is never sacrificed to fit the marker.
        head = head[: max(head_budget - len(marker), 0)].rstrip() + marker
        head = head[:head_budget]
    return head + "\n\n" + tail
