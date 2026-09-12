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
    rows = scores.join(scores.load_records(str(tmp_path)), lambda pid: {"resolved": True, "resolution": "yes", "cp_at_reveal": 0.5})
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
    rows = scores.join(scores.load_records(str(tmp_path)), lambda pid: {"resolved": True, "resolution": "no", "cp_at_reveal": 1.0})
    assert len(rows) == 1
    assert math.isfinite(rows[0]["peer_proxy"])  # Must have finite peer_proxy despite extreme cp
