from __future__ import annotations
import math
import statistics
import numpy as np
from forecasting_tools import NumericDistribution, NumericQuestion
from forecasting_tools.data_models.numeric_report import Percentile
from bot.config import ForecastCfg
from bot.models import ForecastValue, QuestionSummary


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def aggregate_binary(ps: list[float], p_min: float, p_max: float) -> float:
    med = statistics.median(logit(p) for p in ps)
    return min(max(sigmoid(med), p_min), p_max)


def aggregate_mc(dicts: list[dict[str, float]], options: list[str], floor: float) -> dict[str, float]:
    med = {o: statistics.median(d.get(o, 0.0) for d in dicts) for o in options}
    total = sum(med.values())
    n = len(options)
    if total <= 0:
        return {o: 1.0 / n for o in options}
    # A floor of `floor` per option is only satisfiable if reserving it for every option
    # still leaves non-negative mass to distribute (n * floor < 1). Otherwise the floor
    # invariant is impossible to honor alongside sum == 1, so it is dropped entirely
    # (eff_floor = 0) rather than silently violating either contract.
    eff_floor = floor if floor * n < 1 else 0.0
    remaining = 1.0 - n * eff_floor
    # Floor every option, then distribute the remaining mass proportionally to the raw
    # medians. A naive "floor then renormalize by the floored sum" pushes floored values
    # back below the floor (dividing by a sum > 1), so the floor is applied in closed
    # form instead: each option gets `eff_floor` plus its share of what the floor left over.
    return {o: eff_floor + remaining * (v / total) for o, v in med.items()}


def _fake_question(q: QuestionSummary) -> NumericQuestion:
    return NumericQuestion(
        question_text=q.title, lower_bound=q.lower_bound, upper_bound=q.upper_bound,
        open_lower_bound=bool(q.open_lower), open_upper_bound=bool(q.open_upper),
        zero_point=q.zero_point, cdf_size=q.cdf_size or 201,
    )


def percentiles_to_cdf(percentiles: dict[int, float], q: QuestionSummary) -> list[float]:
    pcts = [Percentile(percentile=k / 100, value=float(v)) for k, v in sorted(percentiles.items())]
    dist = NumericDistribution.from_question(pcts, _fake_question(q))
    return [p.percentile for p in dist.get_cdf()]


def _cdf_to_percentiles(cdf: list[float], q: QuestionSummary, targets: list[int]) -> dict[int, float]:
    n = len(cdf)
    xs = np.linspace(q.lower_bound, q.upper_bound, n)
    if q.zero_point is not None:  # log-scaled axis: map linear grid to nominal values
        lo, hi, zp = q.lower_bound, q.upper_bound, q.zero_point
        ratio = (hi - zp) / (lo - zp)
        xs = np.array([zp + (lo - zp) * ratio ** (i / (n - 1)) for i in range(n)])
    # On an open-bounded question the standardized CDF spans only [cdf[0], cdf[-1]]
    # (mass sits outside the bounds), so asking np.interp for a target outside that
    # band silently clamps to the axis end. Several percentiles then collapse onto the
    # same bound value, and the result is no longer a valid distribution: rebuilding a
    # CDF from it either raises or drives the library's PMF rescaling loop degenerate.
    # Clip each target into the achievable band first, then repair any remaining ties.
    lo_h, hi_h = float(cdf[0]), float(cdf[-1])
    out: dict[int, float] = {}
    for t in targets:
        t_eff = min(max(t / 100, lo_h + 1e-6), hi_h - 1e-6)
        out[t] = float(np.interp(t_eff, cdf, xs))
    span = float(xs[-1] - xs[0])
    if q.lower_bound is not None and q.upper_bound is not None:
        span = q.upper_bound - q.lower_bound
    step = max(1e-9 * span, abs(span) * 1e-6)
    prev: float | None = None
    for t in sorted(out):  # walk in percentile order, bumping ties to keep it strictly increasing
        if prev is not None and out[t] <= prev:
            out[t] = prev + step
        prev = out[t]
    return out


def aggregate_numeric(members: list[dict[int, float]], q: QuestionSummary, target_percentiles: list[int]) -> dict[int, float]:
    cdfs = np.array([percentiles_to_cdf(m, q) for m in members])
    med = np.median(cdfs, axis=0)
    med = np.maximum.accumulate(med)  # keep monotone after pointwise median
    return _cdf_to_percentiles(list(med), q, target_percentiles)


def bounded_logit_shift(old_p: float, new_p: float, max_shift: float) -> float:
    lo, ln = logit(old_p), logit(new_p)
    delta = max(-max_shift, min(max_shift, ln - lo))
    return sigmoid(lo + delta)


def bounded_percentile_shift(pre: dict[int, float], revised: dict[int, float], max_fraction: float) -> dict[int, float]:
    """Cap a devil's-advocate numeric revision to a fraction of the pre-DA p90-p10 spread.

    Each percentile present in both dicts may move at most `max_fraction * spread`;
    percentiles the reviser dropped keep their pre-DA value. A zero (or undefined)
    spread gives no scale to bound against, so the raw revision is returned and the
    caller validates it instead.
    """
    if not pre:
        return dict(revised)
    lo = pre.get(10, min(pre.values()))
    hi = pre.get(90, max(pre.values()))
    spread = hi - lo
    if spread <= 0:
        return dict(revised)
    cap = abs(max_fraction) * spread
    out = dict(pre)
    for k, new_v in revised.items():
        if k not in pre:
            continue
        old_v = pre[k]
        out[k] = old_v + max(-cap, min(cap, new_v - old_v))
    return out


def aggregate(values: list[ForecastValue], q: QuestionSummary, cfg: ForecastCfg) -> ForecastValue:
    kind = values[0].kind
    if kind == "binary":
        return ForecastValue(kind="binary", probability=aggregate_binary([v.probability for v in values], cfg.p_min, cfg.p_max))
    if kind == "multiple_choice":
        return ForecastValue(kind="multiple_choice", options=aggregate_mc([v.options for v in values], q.options, cfg.mc_floor))
    return ForecastValue(kind=kind, percentiles=aggregate_numeric([v.percentiles for v in values], q, cfg.numeric_percentiles))
