"""Build docs/dashboard/data.json from run records and scores.csv.

Standard-library only (csv, json, pathlib, datetime) so the GitHub Pages
workflow that runs this needs no dependency install.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

# scores.csv columns that hold text rather than numbers; every other column
# is parsed to float (or None for an empty cell).
_SCORE_STRING_FIELDS = {"kind", "resolution"}


def _format_forecast(fv: dict | None) -> str | None:
    """Render a ForecastValue dict as a short display string."""
    if not fv:
        return None
    if fv.get("probability") is not None:
        return f"{float(fv['probability']):.2f}"
    options = fv.get("options")
    if options:
        name, value = max(options.items(), key=lambda kv: kv[1])
        return f"{name} {float(value):.2f}"
    percentiles = fv.get("percentiles")
    if percentiles:
        p50 = percentiles.get("50", percentiles.get(50))
        if p50 is None:
            # No exact p50 present (shouldn't normally happen) - fall back to
            # whichever percentile is closest to the median.
            key = min(percentiles, key=lambda k: abs(float(k) - 50))
            p50 = percentiles[key]
        try:
            return f"p50={float(p50):.2f}"
        except (TypeError, ValueError):
            return f"p50={p50}"
    return None


def _load_records(runs_path: Path) -> list[dict]:
    """Load every run record, keeping only the latest one per post_id."""
    latest: dict[int, dict] = {}
    for p in sorted(runs_path.glob("**/*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        try:
            post_id = r["question"]["post_id"]
            run_ts = r["run_ts"]
        except (KeyError, TypeError):
            continue
        if post_id not in latest or run_ts > latest[post_id]["run_ts"]:
            latest[post_id] = r
    return list(latest.values())


def _slim(r: dict) -> dict:
    q = r.get("question") or {}
    blind_forecast = (r.get("blind") or {}).get("forecast")
    agg = r.get("aggregate") or {}
    return {
        "post_id": q.get("post_id"),
        "url": q.get("url"),
        "title": q.get("title"),
        "kind": q.get("kind"),
        "run_ts": r.get("run_ts"),
        "final": _format_forecast(r.get("final")),
        "blind": _format_forecast(blind_forecast),
        "pre_da": _format_forecast(agg.get("pre_da")),
        "post_da": _format_forecast(agg.get("post_da")),
        "cost_usd": r.get("cost_usd", 0.0),
        "guards_fired": r.get("guards_fired", []),
        "published": bool(r.get("published", False)),
        "error": r.get("error"),
    }


def _load_scores(scores_path: Path) -> list[dict]:
    if not scores_path.exists():
        return []
    rows = []
    with scores_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            parsed = {}
            for key, value in row.items():
                if key in _SCORE_STRING_FIELDS:
                    parsed[key] = value
                else:
                    parsed[key] = float(value) if value not in (None, "") else None
            rows.append(parsed)
    return rows


def build(runs_dir: str = "runs", out_path: str = "docs/dashboard/data.json") -> dict:
    runs_path = Path(runs_dir)
    records = []
    if runs_path.exists():
        raw = _load_records(runs_path)
        records = [_slim(r) for r in raw]
        records.sort(key=lambda r: r["run_ts"] or "", reverse=True)

    scores = _load_scores(runs_path / "scores.csv")

    result = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "records": records,
        "scores": scores,
    }

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def main() -> None:
    build()


if __name__ == "__main__":
    main()
