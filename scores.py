from __future__ import annotations
import csv
import json
import math
import sys
from pathlib import Path
from typing import Callable
import dotenv
from forecasting_tools import MetaculusClient


def load_records(runs_dir: str) -> list[dict]:
    latest: dict[int, dict] = {}
    for p in sorted(Path(runs_dir).glob("**/*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not r.get("published"):
            continue
        pid = r["question"]["post_id"]
        if pid not in latest or r["run_ts"] > latest[pid]["run_ts"]:
            latest[pid] = r
    return list(latest.values())


def binary_log_score(p: float, resolved_yes: bool) -> float:
    p = min(max(p, 0.001), 0.999)  # Clamp to Metaculus binary range to avoid log(0) domain error
    return math.log(p if resolved_yes else 1 - p)


def peer_vs_community(p: float, cp: float, resolved_yes: bool) -> float:
    return 100 * (binary_log_score(p, resolved_yes) - binary_log_score(cp, resolved_yes))


def _p(node: dict | None) -> float | None:
    return None if not node or node.get("probability") is None else float(node["probability"])


def join(records: list[dict], fetch: Callable[[int], dict]) -> list[dict]:
    rows = []
    for r in records:
        if r["question"]["kind"] != "binary":
            continue  # v1 scores binaries only; numeric/MC come from the Metaculus leaderboard
        info = fetch(r["question"]["post_id"])
        if not info.get("resolved") or info.get("resolution") not in ("yes", "no"):
            continue
        yes = info["resolution"] == "yes"
        blind, pre, post, final = _p((r.get("blind") or {}).get("forecast")), _p((r.get("aggregate") or {}).get("pre_da")), _p((r.get("aggregate") or {}).get("post_da")), _p(r.get("final"))
        cp = info.get("cp_at_reveal")
        rows.append({
            "post_id": r["question"]["post_id"], "kind": "binary", "resolution": info["resolution"], "cp": cp,
            "blind_p": blind, "pre_da_p": pre, "post_da_p": post, "final_p": final,
            "log_score_final": binary_log_score(final, yes) if final is not None else None,
            "log_score_blind": binary_log_score(blind, yes) if blind is not None else None,
            "log_score_pre_da": binary_log_score(pre, yes) if pre is not None else None,
            "peer_proxy": peer_vs_community(final, cp, yes) if (final is not None and cp is not None) else None,
            "cost_usd": r.get("cost_usd", 0.0),
        })
    return rows


def cp_from_question_json(qj: dict) -> float | None:
    """Community prediction (binary) from a Metaculus question JSON, or None if hidden.

    Verified against the live API on 2026-09-13 with the bot token: the aggregation block
    is keyed by the question's `default_aggregation_method` (`recency_weighted` on
    Metaculus Cup questions, `unweighted` on bot tournaments), and for a bot account both
    `latest` and `history` are null on any question the bot did not forecast, and on most
    others too (the API exposes the CP to bots on only ~50 questions unless the Bot
    Benchmarking access tier is granted via the Data Needs Form). So None is the common
    case, not an error; `peer_proxy` stays empty until that access exists.
    """
    try:
        aggs = qj.get("aggregations") or {}
        method = qj.get("default_aggregation_method") or "recency_weighted"
        block = aggs.get(method) or aggs.get("recency_weighted") or aggs.get("unweighted") or {}
        latest = block.get("latest")
        if latest and latest.get("centers"):
            return float(latest["centers"][0])
        hist = block.get("history") or []
        if hist and hist[-1].get("centers"):
            return float(hist[-1]["centers"][0])
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return None


def metaculus_fetch(client: MetaculusClient) -> Callable[[int], dict]:
    def f(post_id: int) -> dict:
        q = client.get_question_by_post_id(post_id)
        res = (q.resolution_string or "").lower() or None
        cp = cp_from_question_json((q.api_json or {}).get("question") or {})
        return {"resolved": res in ("yes", "no"), "resolution": res, "cp_at_reveal": cp}
    return f


def main() -> int:
    dotenv.load_dotenv()
    rows = join(load_records("runs"), metaculus_fetch(MetaculusClient()))
    out = Path("runs/scores.csv")
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["post_id"])
        w.writeheader(); w.writerows(rows)

    def mean(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else float("nan")

    print(f"resolved binaries: {len(rows)}")
    for k in ("log_score_blind", "log_score_pre_da", "log_score_final", "peer_proxy"):
        print(f"{k:18s} mean={mean(k):.4f}")
    print(f"cost per scored question: ${mean('cost_usd'):.3f}")
    print(f"total cost: ${sum(r['cost_usd'] for r in rows):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
