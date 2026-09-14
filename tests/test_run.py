from datetime import datetime, timezone, timedelta
from forecasting_tools import BinaryQuestion
import run


def _q(pid, hours, done=False):
    return BinaryQuestion(question_text="t", id_of_post=pid, id_of_question=pid, close_time=datetime.now(timezone.utc) + timedelta(hours=hours), already_forecasted=done)


def test_select_questions_orders_and_filters(tmp_path):
    qs = [_q(1, 10), _q(2, 1), _q(3, 5, done=True)]
    out = run.select_questions(qs, max_n=5, runs_dir=str(tmp_path))
    assert [q.id_of_post for q in out] == [2, 1]
    assert [q.id_of_post for q in run.select_questions(qs, max_n=1, runs_dir=str(tmp_path))] == [2]


def test_parse_args_modes():
    a = run.parse_args(["--mode", "dry", "--tournament", "bot-testing-area", "--limit", "2"])
    assert a.mode == "dry" and a.tournament == "bot-testing-area" and a.limit == 2


class _FakeMetaculusClient:
    def get_all_open_questions_from_tournament(self, tournament_id_or_slug):
        return [_q(1, 5)]


async def test_run_handles_forecast_question_exception(tmp_path, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(run, "forecast_question", boom)
    monkeypatch.setattr(run, "MetaculusClient", _FakeMetaculusClient)

    args = run.parse_args(["--mode", "dry", "--runs-dir", str(tmp_path)])
    code = await run._run(args)
    assert code == 1


async def test_run_times_out_a_wedged_question(tmp_path, monkeypatch):
    """A question that never finishes must not hold the whole run open."""
    import asyncio
    from bot.config import load_settings

    s = load_settings("config.yaml")
    s.limits.question_wall_clock_s = 0.05

    async def never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(run, "load_settings", lambda path: s)
    monkeypatch.setattr(run, "forecast_question", never_finishes)
    monkeypatch.setattr(run, "MetaculusClient", _FakeMetaculusClient)

    args = run.parse_args(["--mode", "dry", "--runs-dir", str(tmp_path)])
    code = await asyncio.wait_for(run._run(args), timeout=10)
    assert code == 1  # the timeout counts as a guard


def _qq(pid, qid, hours=1, done=False):
    return BinaryQuestion(question_text="t", id_of_post=pid, id_of_question=qid, close_time=datetime.now(timezone.utc) + timedelta(hours=hours), already_forecasted=done)


def test_select_keeps_unpublished_group_sibling(tmp_path):
    from tests.test_comment_records import _rec_for
    from bot import records
    records.write(_rec_for(43322, 43323, True), runs_dir=str(tmp_path))
    out = run.select_questions([_qq(43322, 43323), _qq(43322, 43324)], max_n=5, runs_dir=str(tmp_path))
    assert [q.id_of_question for q in out] == [43324]


def test_select_dedupes_same_question_from_two_tournaments(tmp_path):
    out = run.select_questions([_qq(1, 11), _qq(1, 11)], max_n=5, runs_dir=str(tmp_path))
    assert [q.id_of_question for q in out] == [11]


def test_select_drops_unsupported_types_before_forecasting(tmp_path):
    from forecasting_tools import ConditionalQuestion, DateQuestion
    from forecasting_tools.data_models.questions import MetaculusQuestion
    cond = ConditionalQuestion.model_construct(question_text="c", id_of_post=9, id_of_question=99, close_time=None, already_forecasted=False)
    out = run.select_questions([_qq(1, 11), cond], max_n=5, runs_dir=str(tmp_path))
    assert [q.id_of_question for q in out] == [11]


def test_limit_zero_means_zero(tmp_path):
    assert run.effective_limit(0, 15) == 0
    assert run.effective_limit(None, 15) == 15
    assert run.effective_limit(2, 15) == 2


async def test_in_run_season_cap_stops_launching_questions(tmp_path, monkeypatch):
    # The cap was checked once from disk before the run; a run could then spend well past it.
    from bot.config import load_settings
    from bot.models import ForecastRecord, QuestionSummary

    s = load_settings("config.yaml")
    s.limits.season_usd = 1.0
    s.limits.max_concurrent_questions = 1
    launched = []

    async def cost_sixty_cents(q, *a, **k):
        launched.append(q.id_of_question)
        qs = QuestionSummary(post_id=q.id_of_post, question_id=q.id_of_question, url="u", title="t", kind="binary", close_time=None,
                             options=None, lower_bound=None, upper_bound=None, open_lower=None, open_upper=None,
                             cdf_size=None, zero_point=None, unit=None)
        return ForecastRecord(question=qs, run_ts="2026-09-14T00:00:00+00:00", flags={}, cost_usd=0.6)

    class Client:
        def get_all_open_questions_from_tournament(self, t):
            return [_qq(1, 11), _qq(2, 22), _qq(3, 33)]

    monkeypatch.setattr(run, "load_settings", lambda path: s)
    monkeypatch.setattr(run, "forecast_question", cost_sixty_cents)
    monkeypatch.setattr(run, "MetaculusClient", Client)
    code = await run._run(run.parse_args(["--mode", "dry", "--runs-dir", str(tmp_path)]))
    assert launched == [11, 22]  # third would take the season past $1.00
    assert code == 2
