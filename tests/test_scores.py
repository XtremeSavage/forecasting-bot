import json, math
import pytest
import scores


def test_log_and_peer():
    assert scores.binary_log_score(0.8, True) == pytest.approx(math.log(0.8))
    assert scores.binary_log_score(0.8, False) == pytest.approx(math.log(0.2))
    assert scores.peer_vs_community(0.8, 0.5, True) > 0


def test_join_binary(tmp_path):
    d = tmp_path / "2026-09-12"; d.mkdir()
    rec = {"question": {"post_id": 1, "kind": "binary"}, "published": True, "run_ts": "2026-09-12T00:00:00+00:00",
           "blind": {"forecast": {"kind": "binary", "probability": 0.2}},
           "aggregate": {"pre_da": {"kind": "binary", "probability": 0.3}, "post_da": {"kind": "binary", "probability": 0.35}},
           "final": {"kind": "binary", "probability": 0.35}, "cost_usd": 0.4}
    (d / "1_000000.json").write_text(json.dumps(rec))
    rows = scores.join(scores.load_records(str(tmp_path)), lambda pid, qid=None: {"resolved": True, "resolution": "yes", "cp_at_reveal": 0.5})
    assert len(rows) == 1 and rows[0]["log_score_final"] == math.log(0.35) and rows[0]["log_score_blind"] == math.log(0.2)
    assert rows[0]["peer_proxy"] < 0  # 0.35 vs community 0.5 on a Yes


def test_binary_log_score_clamping():
    # Test that extreme probabilities are clamped to avoid log(0) domain error
    assert scores.binary_log_score(1.0, False) == pytest.approx(math.log(0.001))
    assert math.isfinite(scores.binary_log_score(1.0, False))
    assert math.isfinite(scores.binary_log_score(0.0, True))


def test_join_with_extreme_cp(tmp_path):
    # Test that cp_at_reveal == 1.0 is handled correctly with clamping and cp is not None check
    d = tmp_path / "2026-09-12"; d.mkdir()
    rec = {"question": {"post_id": 2, "kind": "binary"}, "published": True, "run_ts": "2026-09-12T00:00:00+00:00",
           "blind": {"forecast": {"kind": "binary", "probability": 0.3}},
           "aggregate": {"pre_da": {"kind": "binary", "probability": 0.4}, "post_da": {"kind": "binary", "probability": 0.45}},
           "final": {"kind": "binary", "probability": 0.5}, "cost_usd": 0.5}
    (d / "2_000000.json").write_text(json.dumps(rec))
    rows = scores.join(scores.load_records(str(tmp_path)), lambda pid, qid=None: {"resolved": True, "resolution": "no", "cp_at_reveal": 1.0})
    assert len(rows) == 1
    assert math.isfinite(rows[0]["peer_proxy"])  # Must have finite peer_proxy despite extreme cp


def test_load_records_keeps_each_group_subquestion(tmp_path):
    import json
    for qid in (43323, 43324):
        (tmp_path / f"43322_{qid}_x.json").write_text(json.dumps(
            {"question": {"post_id": 43322, "question_id": qid, "kind": "binary"}, "published": True,
             "run_ts": "2026-09-14T00:00:00+00:00", "final": {"probability": 0.5}, "cost_usd": 0.1}), encoding="utf-8")
    recs = scores.load_records(str(tmp_path))
    assert sorted(r["question"]["question_id"] for r in recs) == [43323, 43324]


def test_join_passes_question_id_to_fetch(tmp_path):
    import json
    (tmp_path / "r.json").write_text(json.dumps(
        {"question": {"post_id": 43322, "question_id": 43323, "kind": "binary"}, "published": True,
         "run_ts": "2026-09-14T00:00:00+00:00", "final": {"probability": 0.5}, "cost_usd": 0.1}), encoding="utf-8")
    seen = []
    def fetch(post_id, question_id=None):
        seen.append((post_id, question_id)); return {"resolved": True, "resolution": "yes", "cp_at_reveal": None}
    scores.join(scores.load_records(str(tmp_path)), fetch)
    assert seen == [(43322, 43323)]


def test_metaculus_fetch_resolves_group_subquestion():
    from types import SimpleNamespace
    subs = [SimpleNamespace(id_of_question=43323, resolution_string="Yes", api_json={"question": {}}),
            SimpleNamespace(id_of_question=43324, resolution_string=None, api_json={"question": {}})]
    class C:
        def get_question_by_post_id(self, post_id, group_question_mode="exclude"):
            if group_question_mode == "exclude":
                raise ValueError("Expected 1 question but got 0")
            return subs
    f = scores.metaculus_fetch(C())
    assert f(43322, 43323) == {"resolved": True, "resolution": "yes", "cp_at_reveal": None}
    assert f(43322, 43324)["resolved"] is False
