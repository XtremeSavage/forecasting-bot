import importlib.util
import json
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "docs" / "dashboard" / "build_index.py"
_spec = importlib.util.spec_from_file_location("build_index", _MODULE_PATH)
build_index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_index)


def _write_record(path, post_id, run_ts, final_p=0.5, published=True, kind="binary"):
    if kind == "binary":
        final = {"kind": kind, "probability": final_p}
        blind = {"forecast": {"kind": "binary", "probability": 0.4}}
    else:
        final = {"kind": kind, "percentiles": {"50": final_p}}
        blind = {"forecast": {"kind": kind, "percentiles": {"50": 0.4}}}
    rec = {
        "question": {"post_id": post_id, "url": f"https://example.com/{post_id}", "title": f"Q{post_id}", "kind": kind},
        "run_ts": run_ts,
        "flags": {},
        "blind": blind,
        "aggregate": {
            "pre_da": {"kind": "binary", "probability": 0.45},
            "post_da": {"kind": "binary", "probability": 0.48},
            "method": "avg",
        },
        "final": final,
        "cost_usd": 0.12,
        "guards_fired": [],
        "published": published,
        "error": None,
    }
    path.write_text(json.dumps(rec), encoding="utf-8")


def test_build_basic(tmp_path):
    runs = tmp_path / "runs"
    day = runs / "2026-09-12"
    day.mkdir(parents=True)
    _write_record(day / "1_090000.json", 1, "2026-09-12T09:00:00+00:00", final_p=0.3)
    _write_record(day / "1_100000.json", 1, "2026-09-12T10:00:00+00:00", final_p=0.6)
    _write_record(day / "2_090500.json", 2, "2026-09-12T09:05:00+00:00", final_p=0.7)
    (day / "bad.json").write_text("{not valid json", encoding="utf-8")

    scores_csv = runs / "scores.csv"
    scores_csv.write_text(
        "post_id,kind,resolution,cp,blind_p,pre_da_p,post_da_p,final_p,"
        "log_score_final,log_score_blind,log_score_pre_da,peer_proxy,cost_usd\n"
        "1,binary,yes,0.5,0.4,0.45,0.48,0.6,-0.51,-0.92,-0.80,3.2,0.12\n",
        encoding="utf-8",
    )

    out = tmp_path / "data.json"
    result = build_index.build(runs_dir=str(runs), out_path=str(out))

    assert out.exists()
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == result

    records = result["records"]
    assert len(records) == 2  # post 1 collapsed to its latest record; malformed file skipped

    assert records[0]["run_ts"] >= records[1]["run_ts"]  # newest first

    post1 = next(r for r in records if r["post_id"] == 1)
    assert post1["final"] == "0.60"  # from the newer (10:00) record, not the older 0.3 one
    assert post1["blind"] == "0.40"
    assert post1["pre_da"] == "0.45"
    assert post1["post_da"] == "0.48"
    assert post1["url"] == "https://example.com/1"
    assert post1["title"] == "Q1"
    assert post1["kind"] == "binary"
    assert post1["cost_usd"] == 0.12
    assert post1["guards_fired"] == []
    assert post1["published"] is True
    assert post1["error"] is None

    scores = result["scores"]
    assert len(scores) == 1
    row = scores[0]
    assert row["post_id"] == 1.0
    assert row["kind"] == "binary"
    assert row["resolution"] == "yes"
    assert row["cp"] == 0.5
    assert row["final_p"] == 0.6
    assert row["log_score_final"] == -0.51
    assert row["peer_proxy"] == 3.2


def test_build_missing_runs_dir_and_no_scores(tmp_path):
    out = tmp_path / "data.json"
    result = build_index.build(runs_dir=str(tmp_path / "does_not_exist"), out_path=str(out))

    assert result["records"] == []
    assert result["scores"] == []
    assert "generated" in result
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8")) == result


def test_numeric_label_is_the_true_median_not_p40():
    from docs.dashboard.build_index import _format_forecast
    # Live percentile set has no p50; 40 and 60 straddle it. Was labelled p50=<p40>.
    assert _format_forecast({"kind": "numeric", "percentiles": {"40": 3.47, "60": 3.61}}) == "p50=3.54"
    assert _format_forecast({"kind": "numeric", "percentiles": {"50": 2.0}}) == "p50=2.00"


def test_load_records_keeps_each_group_subquestion(tmp_path):
    from docs.dashboard.build_index import _load_records
    import json
    for qid in (1, 2):
        (tmp_path / f"7_{qid}_x.json").write_text(json.dumps(
            {"question": {"post_id": 7, "question_id": qid, "kind": "binary", "url": "u", "title": "t"}, "published": True,
             "run_ts": "2026-09-14T00:00:00+00:00", "final": {"probability": 0.5}, "cost_usd": 0.1}), encoding="utf-8")
    assert len(_load_records(tmp_path)) == 2
