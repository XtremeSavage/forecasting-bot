import json, time
from bot.guards import consistency_ok, validate_value, drop_invalid_members, enough_members, Budget, season_spent
from bot.models import ForecastValue, MemberForecast, QuestionSummary


def _q(kind="binary", **kw):
    base = dict(post_id=1, question_id=1, url="u", title="t", kind=kind, close_time=None, options=None,
                lower_bound=None, upper_bound=None, open_lower=None, open_upper=None, cdf_size=None, zero_point=None, unit=None)
    base.update(kw)
    return QuestionSummary(**base)


def _m(v, stated=None):
    return MemberForecast(name="a", model="m", forecast=v, reasoning="r", stated_number=stated)


def test_consistency_binary():
    assert consistency_ok(_m(ForecastValue(kind="binary", probability=0.42), stated=0.4))
    assert not consistency_ok(_m(ForecastValue(kind="binary", probability=0.2), stated=0.8))
    assert consistency_ok(_m(ForecastValue(kind="binary", probability=0.2), stated=None))


def test_validate_binary_and_mc():
    assert validate_value(ForecastValue(kind="binary", probability=1.2), _q()) != []
    q = _q("multiple_choice", options=["A", "B"])
    assert validate_value(ForecastValue(kind="multiple_choice", options={"A": 0.5, "B": 0.5}), q) == []
    assert validate_value(ForecastValue(kind="multiple_choice", options={"A": 0.5, "C": 0.5}), q) != []


def test_validate_numeric_bounds():
    q = _q("numeric", lower_bound=0.0, upper_bound=10.0, open_lower=False, open_upper=False)
    assert validate_value(ForecastValue(kind="numeric", percentiles={10: 1.0, 50: 5.0, 90: 9.0}), q) == []
    assert validate_value(ForecastValue(kind="numeric", percentiles={10: 5.0, 50: 4.0, 90: 9.0}), q) != []
    assert validate_value(ForecastValue(kind="numeric", percentiles={10: -1.0, 50: 4.0, 90: 9.0}), q) != []


def test_drop_and_enough():
    good = _m(ForecastValue(kind="binary", probability=0.3), 0.3)
    bad = _m(ForecastValue(kind="binary", probability=0.3), 0.9)
    survivors = drop_invalid_members([good, bad], _q())
    assert survivors == [good] and bad.dropped_reason is not None
    assert not enough_members(survivors, 2) and enough_members(survivors, 1)


def test_budget():
    b = Budget(wall_clock_s=100, per_question_usd=1.0)
    assert b.elapsed_fraction() < 0.05
    assert b.should_skip_da(cost=0.8, frac=0.7) and not b.should_skip_da(cost=0.2, frac=0.7)
    assert b.exhausted(cost=1.01) and not b.exhausted(cost=0.5)


def test_season_spent(tmp_path):
    d = tmp_path / "2026-09-12"; d.mkdir()
    (d / "a.json").write_text(json.dumps({"cost_usd": 0.4}))
    (d / "b.json").write_text(json.dumps({"cost_usd": 0.6}))
    assert season_spent(str(tmp_path)) == 1.0
