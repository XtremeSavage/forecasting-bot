import json
from bot.models import (
    ForecastValue, Forensics, BlindEstimate, Evidence, EvidenceTable,
    MemberForecast, Aggregate, ForecastRecord, QuestionSummary,
)


def test_forecast_value_kinds():
    b = ForecastValue(kind="binary", probability=0.3)
    m = ForecastValue(kind="multiple_choice", options={"A": 0.7, "B": 0.3})
    n = ForecastValue(kind="numeric", percentiles={10: 1.0, 50: 5.0, 90: 9.0})
    assert b.probability == 0.3 and m.options["A"] == 0.7 and n.percentiles[50] == 5.0


def test_record_roundtrip():
    q = QuestionSummary(post_id=1, question_id=2, url="u", title="t", kind="binary",
                        close_time="2026-09-30T00:00:00+00:00", options=None,
                        lower_bound=None, upper_bound=None, open_lower=None, open_upper=None,
                        cdf_size=None, zero_point=None, unit=None)
    rec = ForecastRecord(question=q, run_ts="2026-09-12T00:00:00+00:00", flags={"forensics": True},
                         members=[MemberForecast(name="a", model="m", forecast=ForecastValue(kind="binary", probability=0.4),
                                                 reasoning="r", stated_number=0.4, cost_usd=0.01)],
                         aggregate=Aggregate(pre_da=ForecastValue(kind="binary", probability=0.4), post_da=None, method="logit_median"),
                         cost_usd=0.02, guards_fired=[], published=False)
    s = rec.model_dump_json()
    back = ForecastRecord.model_validate_json(s)
    assert back.members[0].forecast.probability == 0.4
    assert json.loads(s)["question"]["post_id"] == 1
