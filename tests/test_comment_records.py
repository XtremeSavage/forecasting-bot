import json
from pathlib import Path
from bot import comment, records
from bot.models import (ForecastRecord, QuestionSummary, Forensics, BlindEstimate, EvidenceTable, Evidence,
                        ForecastValue, MemberForecast, Aggregate)
from forecasting_tools import BinaryQuestion, NumericQuestion


def _rec():
    q = QuestionSummary(post_id=42, question_id=43, url="https://m/42", title="Will X?", kind="binary", close_time=None, options=None,
                        lower_bound=None, upper_bound=None, open_lower=None, open_upper=None, cdf_size=None, zero_point=None, unit=None)
    return ForecastRecord(
        question=q, run_ts="2026-09-12T10:00:00+00:00", flags={"forensics": True, "devils_advocate": True},
        forensics=Forensics(resolution_statement="Resolves Yes if X by Oct 1.", status_quo_outcome="No"),
        blind=BlindEstimate(reference_class="rc", base_rate_reasoning="br", forecast=ForecastValue(kind="binary", probability=0.2)),
        evidence=EvidenceTable(items=[Evidence(claim="claim one", source="S1", reliability="B", credibility=2, supports="Yes"),
                                      Evidence(claim="claim two", source="S2", reliability="D", credibility=4, supports="No")]),
        members=[MemberForecast(name="a", model="m1", forecast=ForecastValue(kind="binary", probability=0.25), reasoning="x" * 5000),
                 MemberForecast(name="b", model="m2", forecast=ForecastValue(kind="binary", probability=0.3), reasoning="y")],
        aggregate=Aggregate(pre_da=ForecastValue(kind="binary", probability=0.27), post_da=ForecastValue(kind="binary", probability=0.24), method="logit_median", da_critique="crit"),
        final=ForecastValue(kind="binary", probability=0.24), cost_usd=0.31, guards_fired=[], published=False)


def test_comment_contents_and_length():
    c = comment.build(_rec(), 3000)
    assert len(c) <= 3000
    for s in ["Resolves Yes if X by Oct 1.", "0.20", "claim one", "B2", "0.27", "0.24", "Final", "a, b"]:
        assert s in c
    assert "x" * 100 not in c  # member reasoning is not dumped into the comment


def test_comment_truncation_keeps_final():
    rec = _rec()
    rec.forensics.resolution_statement = "z" * 5000
    c = comment.build(rec, 3000)
    assert len(c) <= 3000
    assert "**Final:** 0.24" in c
    assert "[truncated]" in c
    assert "cost=$0.31" in c


def test_write_and_local_check(tmp_path):
    rec = _rec()
    rec.published = True
    p = records.write(rec, runs_dir=str(tmp_path))
    assert Path(p).exists() and "2026-09-12" in p and "42_" in p
    assert json.loads(Path(p).read_text())["final"]["probability"] == 0.24
    assert records.already_forecasted_locally(42, None, str(tmp_path))
    assert not records.already_forecasted_locally(7, None, str(tmp_path))

    rec2 = _rec()
    rec2.question.post_id = 43
    rec2.published = False
    records.write(rec2, runs_dir=str(tmp_path))
    assert not records.already_forecasted_locally(43, None, str(tmp_path))


def test_question_summary_binary_and_numeric():
    bq = BinaryQuestion(question_text="t", id_of_post=1, id_of_question=2, page_url="u")
    nq = NumericQuestion(question_text="t", id_of_post=3, id_of_question=4, lower_bound=0.0, upper_bound=10.0,
                          open_lower_bound=False, open_upper_bound=True)

    bs = records.question_summary(bq)
    assert bs.kind == "binary"
    assert bs.post_id == 1
    assert bs.question_id == 2

    ns = records.question_summary(nq)
    assert ns.kind == "numeric"
    assert ns.post_id == 3
    assert ns.question_id == 4
    assert ns.lower_bound == 0.0
    assert ns.upper_bound == 10.0


def test_comment_fits_a_very_small_budget():
    # The tail alone (final forecast + footer) can exceed a tiny max_chars; the old cut
    # arithmetic went negative and sliced the head from the wrong end.
    assert len(comment.build(_rec(), 200)) <= 200
    assert len(comment.build(_rec(), 40)) <= 40
    assert len(comment.build(_rec(), 10)) <= 10


def _rec_for(post_id, question_id, published, ts="2026-09-14T00:51:13+00:00"):
    r = _rec()
    r.question.post_id, r.question.question_id, r.published, r.run_ts = post_id, question_id, published, ts
    return r


def test_identity_is_per_subquestion_not_per_post(tmp_path):
    # Live 2026-09-14: post 43322 is a question group with subquestions 43323 (published) and
    # 43324 (never run). Keying on post_id alone made 43324 look already forecast forever.
    records.write(_rec_for(43322, 43323, True), runs_dir=str(tmp_path))
    assert records.already_forecasted_locally(43322, 43323, str(tmp_path))
    assert not records.already_forecasted_locally(43322, 43324, str(tmp_path))


def test_sibling_records_in_same_second_do_not_overwrite(tmp_path):
    a = records.write(_rec_for(5, 51, True), runs_dir=str(tmp_path))
    b = records.write(_rec_for(5, 52, False), runs_dir=str(tmp_path))
    assert a != b
    assert records.already_forecasted_locally(5, 51, str(tmp_path))
    assert not records.already_forecasted_locally(5, 52, str(tmp_path))


def test_legacy_filename_records_still_recognised(tmp_path):
    # Records written before 2026-09-14 are named {post_id}_{HHMMSS}.json; identity must
    # come from the JSON body, not the filename.
    import json
    d = tmp_path / "2026-09-13"; d.mkdir()
    (d / "43322_215415.json").write_text(_rec_for(43322, 43323, True).model_dump_json(), encoding="utf-8")
    assert records.already_forecasted_locally(43322, 43323, str(tmp_path))
    assert not records.already_forecasted_locally(43322, 43324, str(tmp_path))
