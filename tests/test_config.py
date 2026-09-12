from bot.config import load_settings, Settings


def test_load_settings_defaults():
    s = load_settings("config.yaml")
    assert isinstance(s, Settings)
    assert s.stages.forensics is True
    assert s.limits.per_question_usd == 1.0
    assert len(s.models.members) == 4
    assert s.models.members[0].model == "openai/gpt-5.4"
    assert s.forecast.p_min == 0.01
    assert s.tournaments.fall == 33121


def test_settings_override(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(open("config.yaml").read().replace("devils_advocate: true", "devils_advocate: false"))
    s = load_settings(str(p))
    assert s.stages.devils_advocate is False
