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


def percentiles_to_cdf(percentiles: dict[int, float], q: QuestionSummary, *, standardize: bool = True) -> list[float]:
    """Percentiles -> 201-point CDF on the question's grid.

    With `standardize=True` (the default, used by the publisher and the guards) the library
    applies Metaculus's submission rules: a 1% uniform floor across the whole range, minimum
    slope, capped PMF. That floor visibly widens the tails (on a 1-7 range it moves p5 down
    ~0.27 and p95 up ~0.5), and it compounds every time a CDF is read back to percentiles and
    rebuilt. It must therefore be applied exactly once, at publish. Internal aggregation
    passes `standardize=False` to get the raw piecewise-linear CDF (bounds handled, no floor).
    """
    pcts = [Percentile(percentile=k / 100, value=float(v)) for k, v in sorted(percentiles.items())]
    dist = NumericDistribution.from_question(pcts, _fake_question(q), standardize_cdf=standardize)
    if standardize:
        return [p.percentile for p in dist.get_cdf()]
    # Raw path: evaluate the library's piecewise-linear CDF (bounds handled inside
    # _get_cdf_at) on the same grid, but skip its re-validation, which rejects the
    # float noise (1.0000000000000007) the un-standardized path can produce on
    # log-scaled questions. Clamp and round instead.
    n = dist.cdf_size or 201
    raw = [dist._get_cdf_at(i / (n - 1)) for i in range(n)]
    return [min(max(round(float(v), 10), 0.0), 1.0) for v in raw]


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
    # Slopes of the first and last grid segments (x per unit of CDF), used to extend the
    # piecewise-linear CDF past an OPEN bound. A target below cdf[0] means the ensemble
    # puts that much mass below the lower bound; clipping it to the edge (the old
    # behaviour) made the publish rebuild put a PMF spike at the bound that no member had.
    # Linear extension keeps the in-range percentiles exact and the mass outside intact.
    # The library is piecewise-linear in its 0..1 "cdf location" space (a log-scaled axis
    # is mapped from there), so extend in location units and map back; that reproduces a
    # member's own out-of-range percentile exactly on either axis type. Clamp to inside
    # the library's hard tolerance (2x the range past a bound) so the result always builds.
    dcdf_lo = float(cdf[1] - cdf[0]) if n > 1 else 0.0
    dcdf_hi = float(cdf[-1] - cdf[-2]) if n > 1 else 0.0
    dloc = 1.0 / (n - 1) if n > 1 else 0.0
    span_lim = (q.upper_bound - q.lower_bound) * 1.9

    def nominal(loc: float) -> float:
        if q.zero_point is None:
            return q.lower_bound + (q.upper_bound - q.lower_bound) * loc
        ratio = (q.upper_bound - q.zero_point) / (q.lower_bound - q.zero_point)
        return q.lower_bound + (q.upper_bound - q.lower_bound) * (ratio ** loc - 1) / (ratio - 1)

    for t in targets:
        tt = t / 100
        if tt < lo_h and q.open_lower and dcdf_lo > 0:
            out[t] = max(float(nominal(-(lo_h - tt) / dcdf_lo * dloc)), q.lower_bound - span_lim)
        elif tt > hi_h and q.open_upper and dcdf_hi > 0:
            out[t] = min(float(nominal(1.0 + (tt - hi_h) / dcdf_hi * dloc)), q.upper_bound + span_lim)
        else:
            t_eff = min(max(tt, lo_h + 1e-6), hi_h - 1e-6)
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
    # Raw (un-standardized) member CDFs: the Metaculus floor is applied once, by the publisher.
    cdfs = np.array([percentiles_to_cdf(m, q, standardize=False) for m in members])
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
