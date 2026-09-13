import pytest
from bot.aggregate import (logit, sigmoid, aggregate_binary, aggregate_mc, aggregate_numeric,
                           bounded_logit_shift, bounded_percentile_shift, aggregate, percentiles_to_cdf)
from bot.models import ForecastValue, QuestionSummary
from bot.config import ForecastCfg


def _q(kind="numeric", lo=0.0, hi=100.0, open_lo=False, open_hi=False, cdf_size=201, zero_point=None):
    return QuestionSummary(post_id=1, question_id=1, url="u", title="t", kind=kind, close_time=None,
                           options=["A", "B", "C"] if kind == "multiple_choice" else None,
                           lower_bound=lo, upper_bound=hi, open_lower=open_lo, open_upper=open_hi,
                           cdf_size=cdf_size, zero_point=zero_point, unit=None)


def test_logit_roundtrip():
    assert sigmoid(logit(0.3)) == pytest.approx(0.3)


def test_binary_logit_median_and_clamp():
    assert aggregate_binary([0.2, 0.3, 0.9], 0.01, 0.99) == pytest.approx(0.3)
    assert aggregate_binary([0.2, 0.8], 0.01, 0.99) == pytest.approx(0.5)  # logit median of symmetric pair
    assert aggregate_binary([0.999, 0.999], 0.01, 0.99) == 0.99
    assert aggregate_binary([0.0001], 0.01, 0.99) == 0.01


def test_mc_median_floor_renormalize():
    out = aggregate_mc([{"A": 0.9, "B": 0.1, "C": 0.0}, {"A": 0.8, "B": 0.2, "C": 0.0}], ["A", "B", "C"], 0.01)
    assert out["C"] >= 0.01 and sum(out.values()) == pytest.approx(1.0)
    assert out["A"] > out["B"] > out["C"]


def test_percentiles_to_cdf_shape():
    cdf = percentiles_to_cdf({10: 20.0, 50: 50.0, 90: 80.0}, _q())
    assert len(cdf) == 201 and cdf[0] == pytest.approx(0.0) and cdf[-1] == pytest.approx(1.0)
    assert all(b >= a for a, b in zip(cdf, cdf[1:]))


def test_numeric_pointwise_median():
    m = [{10: 10.0, 50: 50.0, 90: 90.0}, {10: 20.0, 50: 60.0, 90: 95.0}, {10: 15.0, 50: 55.0, 90: 92.0}]
    out = aggregate_numeric(m, _q(), [10, 50, 90])
    assert 12 < out[10] < 18 and 52 < out[50] < 58 and 90 < out[90] < 94


def test_mc_floor_infeasible_drops_floor_two_options():
    # floor * n >= 1 (0.6 * 2 = 1.2): the floor invariant can't be met, so it is dropped
    # rather than violating sum == 1 or collapsing the ordering.
    out = aggregate_mc([{"A": 0.9, "B": 0.1}], ["A", "B"], 0.6)
    assert sum(out.values()) == pytest.approx(1.0)
    assert out["A"] > out["B"]


def test_mc_floor_infeasible_drops_floor_three_options():
    # floor * n >= 1 (0.5 * 3 = 1.5): same as above, with three options.
    out = aggregate_mc([{"A": 0.6, "B": 0.3, "C": 0.1}], ["A", "B", "C"], 0.5)
    assert sum(out.values()) == pytest.approx(1.0)
    assert out["A"] > out["B"] > out["C"]


def test_bounded_shift():
    assert bounded_logit_shift(0.5, 0.9, 0.5) == pytest.approx(sigmoid(0.5))
    assert bounded_logit_shift(0.5, 0.55, 0.5) == pytest.approx(0.55)


def test_aggregate_dispatch():
    cfg = ForecastCfg()
    v = aggregate([ForecastValue(kind="binary", probability=0.2), ForecastValue(kind="binary", probability=0.4)], _q("binary"), cfg)
    assert v.kind == "binary" and 0.2 < v.probability < 0.4


SPREAD_MEMBER = {5: -40.0, 10: -20.0, 20: 0.0, 40: 20.0, 60: 40.0, 80: 60.0, 90: 80.0, 95: 95.0}
PCTS = [5, 10, 20, 40, 60, 80, 90, 95]


def test_open_bounds_do_not_collapse_percentiles_onto_the_bound():
    # Members putting real mass outside both bounds: the standardized CDF then spans only
    # part of [0, 1], and interpolating the 5th/10th percentile used to clamp both onto
    # the lower bound. The duplicate values made the result unusable as a distribution.
    q = _q(open_lo=True, open_hi=True)
    out = aggregate_numeric([SPREAD_MEMBER, SPREAD_MEMBER, SPREAD_MEMBER], q, PCTS)
    vals = [out[k] for k in sorted(out)]
    assert all(b > a for a, b in zip(vals, vals[1:])), vals
    cdf = percentiles_to_cdf(out, q)  # the round trip the publisher makes; used to raise
    assert len(cdf) == 201
    assert all(b >= a for a, b in zip(cdf, cdf[1:]))


def test_open_bounds_with_zero_point_round_trip():
    # Log-scaled axis (zero_point set), open on both sides, with a member whose top
    # percentile sits above the upper bound.
    q = _q(lo=1.0, hi=1000.0, open_lo=True, open_hi=True, zero_point=0.0)
    m = {5: 2.0, 10: 5.0, 20: 10.0, 40: 50.0, 60: 100.0, 80: 400.0, 90: 800.0, 95: 1500.0}
    out = aggregate_numeric([m, m, m], q, PCTS)
    vals = [out[k] for k in sorted(out)]
    assert all(b > a for a, b in zip(vals, vals[1:])), vals
    assert 1.0 <= vals[0] and vals[-1] <= 1000.0  # interpolation stays on the question's axis
    cdf = percentiles_to_cdf(out, q)
    assert len(cdf) == 201
    assert all(b >= a for a, b in zip(cdf, cdf[1:]))


def test_closed_bounds_round_trip_still_monotone():
    q = _q(lo=1.0, hi=1000.0, open_lo=False, open_hi=False, zero_point=0.0)
    m = {5: 5.0, 10: 20.0, 20: 60.0, 40: 150.0, 60: 300.0, 80: 600.0, 90: 800.0, 95: 950.0}
    out = aggregate_numeric([m, m, m], q, PCTS)
    vals = [out[k] for k in sorted(out)]
    assert all(b > a for a, b in zip(vals, vals[1:])), vals
    cdf = percentiles_to_cdf(out, q)
    assert len(cdf) == 201 and all(b >= a for a, b in zip(cdf, cdf[1:]))


def test_bounded_percentile_shift_caps_move_to_fraction_of_spread():
    pre = {10: 0.0, 50: 50.0, 90: 100.0}  # p90 - p10 spread of 100
    huge = {10: 0.0, 50: 500.0, 90: 100.0}
    assert bounded_percentile_shift(pre, huge, 0.25)[50] == pytest.approx(75.0)
    assert bounded_percentile_shift(pre, {10: 0.0, 50: -500.0, 90: 100.0}, 0.25)[50] == pytest.approx(25.0)
    # A move inside the cap passes through untouched, and dropped keys keep the pre value.
    partial = bounded_percentile_shift(pre, {50: 60.0}, 0.25)
    assert partial == {10: 0.0, 50: 60.0, 90: 100.0}


def test_bounded_percentile_shift_with_no_spread_returns_revision():
    flat = {10: 5.0, 50: 5.0, 90: 5.0}
    revised = {10: 1.0, 50: 5.0, 90: 9.0}
    assert bounded_percentile_shift(flat, revised, 0.25) == revised


def test_numeric_aggregate_does_not_prestandardize_tails():
    # Regression for the first paid dry run (2026-09-13, question 43322): every member was
    # pushed through the library's Metaculus standardization (a 1% uniform floor over the
    # whole range) before the median, then again at publish. Each pass moved p5 down ~0.27
    # and p95 up ~0.5 on a 1-7 range, so the posted tails were far wider than any member's.
    # Aggregating identical members must return those members' percentiles, tails included.
    q = _q().model_copy(update={"lower_bound": 1.0, "upper_bound": 7.0, "open_lower": False, "open_upper": False})
    m = {5: 3.0, 10: 3.08, 20: 3.2, 40: 3.39, 60: 3.58, 80: 3.84, 90: 4.03, 95: 4.18}
    out = aggregate_numeric([m, m, m, m], q, sorted(m))
    for k, v in m.items():
        assert out[k] == pytest.approx(v, abs=0.02), f"p{k}: {out[k]} vs member {v}"
