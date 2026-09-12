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
    parts = ["**Resolution forensics.** " + (rec.forensics.resolution_statement if rec.forensics else "stage off")]
    if rec.forensics:
        parts.append(f"Status quo: {rec.forensics.status_quo_outcome}. Traps: {'; '.join(rec.forensics.traps[:3]) or 'none noted'}.")
    if rec.blind:
        parts.append(f"**Blind base rate.** {rec.blind.reference_class}. Estimate {_fmt(rec.blind.forecast)}.")
    if rec.evidence and rec.evidence.items:
        top = sorted(rec.evidence.items, key=lambda e: (e.reliability, e.credibility))[:3]
        parts.append("**Key evidence.** " + " | ".join(f"[{e.reliability}{e.credibility}] {e.claim} ({e.source})" for e in top))
    if rec.aggregate:
        names = ", ".join(m.name for m in rec.members if m.dropped_reason is None)
        parts.append(f"**ACH ensemble** ({names}): {_fmt(rec.aggregate.pre_da)} via {rec.aggregate.method}.")
        if rec.aggregate.post_da is not None:
            parts.append(f"**Devil's advocate** moved it to {_fmt(rec.aggregate.post_da)}.")
    parts.append(f"**Final:** {_fmt(rec.final)}")
    flags = ",".join(k for k, v in rec.flags.items() if v)
    parts.append(f"_bot=XtremeSavageForecast stages={flags} cost=${rec.cost_usd:.2f}_")
    text = "\n\n".join(parts)
    if len(text) > max_chars:
        text = text[: max_chars - 15].rstrip() + "\n\n[truncated]"
    return text
