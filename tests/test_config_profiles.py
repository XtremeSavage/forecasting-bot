"""Every shipped config profile must load and be runnable."""
import pytest
from bot.config import load_settings

PROFILES = ["config.yaml", "config.lean.yaml"]


@pytest.mark.parametrize("path", PROFILES)
def test_profile_loads_and_is_runnable(path):
    s = load_settings(path)
    assert len(s.models.members) >= s.limits.min_members
    assert s.limits.per_call_usd <= s.limits.per_question_usd <= s.limits.season_usd
    assert s.tournaments.fall == 33121
    assert s.tournaments.test == "bot-testing-area"


def test_lean_is_cheaper_than_default():
    d, l = load_settings("config.yaml"), load_settings("config.lean.yaml")
    assert len(l.models.members) < len(d.models.members)
    assert l.limits.per_question_usd < d.limits.per_question_usd
    assert l.limits.season_usd < d.limits.season_usd
    assert l.research.max_queries < d.research.max_queries
