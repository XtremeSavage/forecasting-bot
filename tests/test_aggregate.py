import pytest
from bot.aggregate import (logit, sigmoid, aggregate_binary, aggregate_mc, aggregate_numeric,
                           bounded_logit_shift, aggregate, percentiles_to_cdf)
from bot.models import ForecastValue, QuestionSummary
from bot.config import ForecastCfg


def _q(kind="numeric", lo=0.0, hi=100.0, open_lo=False, open_hi=False, cdf_size=201):
    return QuestionSummary(post_id=1, question_id=1, url="u", title="t", kind=kind, close_time=None,
                           options=["A", "B", "C"] if kind == "multiple_choice" else None,
                           lower_bound=lo, upper_bound=hi, open_lower=open_lo, open_upper=open_hi,
                           cdf_size=cdf_size, zero_point=None, unit=None)


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


def test_bounded_shift():
    assert bounded_logit_shift(0.5, 0.9, 0.5) == pytest.approx(sigmoid(0.5))
    assert bounded_logit_shift(0.5, 0.55, 0.5) == pytest.approx(0.55)


def test_aggregate_dispatch():
    cfg = ForecastCfg()
    v = aggregate([ForecastValue(kind="binary", probability=0.2), ForecastValue(kind="binary", probability=0.4)], _q("binary"), cfg)
    assert v.kind == "binary" and 0.2 < v.probability < 0.4
