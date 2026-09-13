"""Community-prediction extraction, shaped like real API responses seen 2026-09-13."""
from scores import cp_from_question_json


def test_cp_hidden_returns_none():
    # Bot tournament, resolved, bot did not forecast: block present, contents null.
    assert cp_from_question_json({"default_aggregation_method": "unweighted",
                                  "aggregations": {"unweighted": {"history": None, "latest": None}}}) is None
    assert cp_from_question_json({}) is None


def test_cp_uses_declared_method_latest_then_history():
    q = {"default_aggregation_method": "unweighted",
         "aggregations": {"recency_weighted": {"latest": {"centers": [0.9]}},
                          "unweighted": {"latest": {"centers": [0.42]}, "history": [{"centers": [0.1]}]}}}
    assert cp_from_question_json(q) == 0.42
    q["aggregations"]["unweighted"]["latest"] = None
    assert cp_from_question_json(q) == 0.1


def test_cp_falls_back_to_recency_weighted_when_method_missing():
    q = {"aggregations": {"recency_weighted": {"history": [{"centers": [0.7]}]}}}
    assert cp_from_question_json(q) == 0.7
