import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from forecasting_tools import BinaryQuestion, DateQuestion, MultipleChoiceQuestion, NumericQuestion
from forecasting_tools.data_models.questions import QuestionState
from bot.config import load_settings
from bot import pipeline
from bot.models import ForecastValue, QuestionSummary

FOR = '```json\n{"resolution_statement": "r", "status_quo_outcome": "No", "search_queries": ["q"]}\n```'
BLIND = '```json\n{"reference_class": "rc", "base_rate_reasoning": "br", "forecast": {"probability": 0.2}}\n```'
EVID = '```json\n{"items": [], "already_resolved_signal": ""}\n```'


def member(p):
    return f'reasoning\nFINAL: {p}\n```json\n{{"probability": {p}}}\n```'


CRIT = "critique text"
REV = '```json\n{"probability": 0.9}\n```'


class FakeLlm:
    def __init__(self, texts):
        self.texts = list(texts); self.total_cost_usd = 0.0; self.fallback_used = False

    async def complete(self, prompt, model, temperature=0.5, system=None, max_tokens=4000):
        from bot.llm import LlmResult
        self.total_cost_usd += 0.01
        return LlmResult(text=self.texts.pop(0), model=model, cost_usd=0.01, prompt_tokens=1, completion_tokens=1, provider="openrouter")

    async def complete_json(self, prompt, model, out_type, temperature=0.5, retries=1, system=None, max_tokens=4000):
        from bot.llm import extract_json
        res = await self.complete(prompt, model, temperature, system, max_tokens)
        return out_type.model_validate(extract_json(res.text)), res


class FakePublisher:
    def __init__(self, open_=True):
        self.open_ = open_; self.published = []

    def is_open(self, post_id, question_id=None):
        return self.open_

    def publish(self, q, value, comment):
        self.published.append((q.post_id, value, comment))


def _bq():
    return BinaryQuestion(question_text="Will X?", id_of_post=5, id_of_question=6, page_url="https://m/5",
                          background_info="bg", resolution_criteria="crit https://src.example/x", fine_print="fp")


async def test_full_binary_run_with_bounded_da(tmp_path):
    s = load_settings("config.yaml")
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    texts = [FOR, BLIND, EVID, member(0.2), member(0.3), member(0.25), member(0.22), CRIT, REV]
    llm = FakeLlm(texts)
    pub = FakePublisher()
    rec = await pipeline.forecast_question(_bq(), s, llm, pub, "2026-09-12", runs_dir=str(tmp_path))
    assert rec.published and len(pub.published) == 1
    pre = rec.aggregate.pre_da.probability
    assert 0.2 <= pre <= 0.3
    # DA wanted 0.9 but the move is bounded to 0.5 logits
    assert rec.final.probability < 0.45 and rec.final.probability > pre
    assert rec.error is None and rec.cost_usd > 0
    assert list(Path(tmp_path).glob("**/5_*.json"))


async def test_skip_when_too_few_members(tmp_path):
    s = load_settings("config.yaml")
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    s.models.members = s.models.members[:2]
    texts = [FOR, BLIND, EVID, member(0.2), "no json at all"]
    rec = await pipeline.forecast_question(_bq(), s, FakeLlm(texts), FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    assert not rec.published and "SKIP_MIN_MEMBERS" in rec.guards_fired
    assert list(Path(tmp_path).glob("**/5_*.json"))


async def test_publish_gate_closed(tmp_path):
    s = load_settings("config.yaml")
    s.stages.devils_advocate = False
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    texts = [FOR, BLIND, EVID, member(0.2), member(0.3), member(0.25), member(0.22)]
    rec = await pipeline.forecast_question(_bq(), s, FakeLlm(texts), FakePublisher(open_=False), "2026-09-12", runs_dir=str(tmp_path))
    assert not rec.published and "PUBLISH_SKIPPED_CLOSED" in rec.guards_fired


async def test_dry_run_writes_record_without_publishing(tmp_path):
    s = load_settings("config.yaml")
    s.stages.devils_advocate = False
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    texts = [FOR, BLIND, EVID, member(0.2), member(0.3), member(0.25), member(0.22)]
    rec = await pipeline.forecast_question(_bq(), s, FakeLlm(texts), None, "2026-09-12", runs_dir=str(tmp_path))
    assert not rec.published and rec.final is not None and rec.comment
    assert list(Path(tmp_path).glob("**/5_*.json"))


async def test_ach_off_skips_publish(tmp_path):
    s = load_settings("config.yaml")
    s.stages.ach_forecast = False
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    texts = [FOR, BLIND, EVID]
    rec = await pipeline.forecast_question(_bq(), s, FakeLlm(texts), FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    assert not rec.published
    assert "SKIP_ACH_OFF" in rec.guards_fired
    assert rec.error is None


class RaisingLlm(FakeLlm):
    """Raises on the Nth call (1-indexed), still booking the 0.01 cost first."""

    def __init__(self, texts, raise_at):
        super().__init__(texts)
        self.raise_at = raise_at
        self.calls = 0

    async def complete(self, prompt, model, temperature=0.5, system=None, max_tokens=4000):
        self.calls += 1
        if self.calls == self.raise_at:
            self.total_cost_usd += 0.01
            raise RuntimeError("boom")
        return await super().complete(prompt, model, temperature, system, max_tokens)


async def test_cost_counts_failed_member_calls(tmp_path):
    s = load_settings("config.yaml")
    s.stages.devils_advocate = False
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    # forensics, blind, evidence = calls 1-3; members = calls 4-7 (4th member = call 7)
    texts = [FOR, BLIND, EVID, member(0.2), member(0.3), member(0.25)]
    llm = RaisingLlm(texts, raise_at=7)
    rec = await pipeline.forecast_question(_bq(), s, llm, FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    assert rec.published
    assert rec.cost_usd == pytest.approx(llm.total_cost_usd)


async def test_provider_fallback_not_sticky(tmp_path):
    s = load_settings("config.yaml")
    s.stages.devils_advocate = False
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    texts = [FOR, BLIND, EVID, member(0.2), member(0.3), member(0.25), member(0.22)]
    llm = FakeLlm(texts)
    llm.fallback_used = True
    rec = await pipeline.forecast_question(_bq(), s, llm, FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    assert "PROVIDER_FALLBACK" not in rec.guards_fired


async def test_da_failure_keeps_pre_and_publishes(tmp_path):
    s = load_settings("config.yaml")
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    texts = [FOR, BLIND, EVID, member(0.2), member(0.3), member(0.25), member(0.22), "no json", "no json"]
    rec = await pipeline.forecast_question(_bq(), s, FakeLlm(texts), FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    assert rec.published
    assert "DA_FAILED" in rec.guards_fired
    assert rec.final.probability == pytest.approx(rec.aggregate.pre_da.probability)


# --------------------------------------------------------------------------
# Numeric and multiple-choice end to end, plus the publisher wiring. These are
# the paths that had never been exercised outside binary questions.
# --------------------------------------------------------------------------

NUM = {"5": 10.0, "10": 15.0, "20": 25.0, "40": 40.0, "60": 55.0, "80": 70.0, "90": 80.0, "95": 90.0}
BLIND_NUM = ('```json\n{"reference_class": "rc", "base_rate_reasoning": "br", "forecast": '
             '{"percentiles": {"5": 5, "10": 12, "20": 22, "40": 38, "60": 52, "80": 68, "90": 78, "95": 88}}}\n```')
BLIND_MC = ('```json\n{"reference_class": "rc", "base_rate_reasoning": "br", "forecast": '
            '{"options": {"A": 0.5, "B": 0.3, "C": 0.2}}}\n```')
REV_NUM = ('```json\n{"percentiles": {"5": 60, "10": 65, "20": 70, "40": 75, '
           '"60": 80, "80": 85, "90": 90, "95": 95}}\n```')
REV_MC = '```json\n{"options": {"A": 0.98, "B": 0.01, "C": 0.01}}\n```'


def numeric_member(shift=0.0):
    d = {k: v + shift for k, v in NUM.items()}
    return f'reasoning\nFINAL: {d["40"]}\n```json\n{json.dumps({"percentiles": d})}\n```'


def mc_member(a):
    rest = (1.0 - a) / 2
    d = {"A": a, "B": rest, "C": rest}
    return f'reasoning\nFINAL: {max(d.values())}\n```json\n{json.dumps({"options": d})}\n```'


def _nq(open_lo=False, open_hi=False):
    return NumericQuestion(question_text="How many X?", id_of_post=8, id_of_question=9, page_url="https://m/8",
                           background_info="bg", resolution_criteria="crit", fine_print="fp",
                           lower_bound=0.0, upper_bound=100.0, open_lower_bound=open_lo, open_upper_bound=open_hi)


def _mcq():
    return MultipleChoiceQuestion(question_text="Which X?", id_of_post=10, id_of_question=11, page_url="https://m/10",
                                  background_info="bg", resolution_criteria="crit", fine_print="fp",
                                  options=["A", "B", "C"])


def _dq():
    return DateQuestion(question_text="When X?", id_of_post=12, id_of_question=13, page_url="https://m/12",
                        background_info="bg", resolution_criteria="crit", fine_print="fp",
                        lower_bound=datetime(2026, 1, 1, tzinfo=timezone.utc),
                        upper_bound=datetime(2027, 1, 1, tzinfo=timezone.utc),
                        open_lower_bound=False, open_upper_bound=False)


def _offline(s):
    s.research.asknews_enabled = s.research.web_search_enabled = s.research.resolution_fetch_enabled = False
    return s


async def test_numeric_end_to_end_publishes_a_monotone_distribution(tmp_path):
    s = _offline(load_settings("config.yaml"))
    s.stages.devils_advocate = False
    texts = [FOR, BLIND_NUM, EVID] + [numeric_member(d) for d in (0, 2, -2, 1)]
    pub = FakePublisher()
    rec = await pipeline.forecast_question(_nq(), s, FakeLlm(texts), pub, "2026-09-12", runs_dir=str(tmp_path))
    assert rec.error is None
    assert "AGGREGATE_INVALID" not in rec.guards_fired
    assert rec.published and len(pub.published) == 1
    vals = [rec.final.percentiles[k] for k in sorted(rec.final.percentiles)]
    assert all(b > a for a, b in zip(vals, vals[1:])), vals
    assert vals[0] >= 0.0 and vals[-1] <= 100.0
    posted = pub.published[0][1]
    assert posted.kind == "numeric" and posted.percentiles == rec.final.percentiles
    assert list(Path(tmp_path).glob("**/8_*.json"))


async def test_multiple_choice_end_to_end_publishes_normalized_options(tmp_path):
    s = _offline(load_settings("config.yaml"))
    s.stages.devils_advocate = False
    texts = [FOR, BLIND_MC, EVID] + [mc_member(a) for a in (0.5, 0.6, 0.55, 0.45)]
    pub = FakePublisher()
    rec = await pipeline.forecast_question(_mcq(), s, FakeLlm(texts), pub, "2026-09-12", runs_dir=str(tmp_path))
    assert rec.error is None and rec.published and len(pub.published) == 1
    assert set(rec.final.options) == {"A", "B", "C"}
    assert sum(rec.final.options.values()) == pytest.approx(1.0)
    assert rec.final.options["A"] > rec.final.options["B"]
    assert pub.published[0][1].kind == "multiple_choice"


async def test_date_question_is_skipped_before_any_llm_call(tmp_path):
    # Date questions are not supported. FakeLlm has no texts, so any stage that ran
    # would raise IndexError instead of reaching the guard.
    s = load_settings("config.yaml")
    llm = FakeLlm([])
    pub = FakePublisher()
    rec = await pipeline.forecast_question(_dq(), s, llm, pub, "2026-09-12", runs_dir=str(tmp_path))
    assert rec.guards_fired == ["SKIP_DATE_UNSUPPORTED"]
    assert not rec.published and pub.published == []
    assert rec.error is None and llm.total_cost_usd == 0.0
    assert list(Path(tmp_path).glob("**/12_*.json"))  # the record is still written


async def test_evidence_stage_failure_still_publishes(tmp_path):
    # The evidence stage replies with non-JSON twice (complete_json retries once).
    s = _offline(load_settings("config.yaml"))
    s.stages.devils_advocate = False
    texts = [FOR, BLIND, "not json", "still not json"] + [member(p) for p in (0.2, 0.3, 0.25, 0.22)]
    rec = await pipeline.forecast_question(_bq(), s, FakeLlm(texts), FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    assert "EVIDENCE_FAILED" in rec.guards_fired
    assert rec.published and rec.evidence is None and rec.error is None


async def test_forensics_and_blind_failures_fall_back_and_publish(tmp_path):
    s = _offline(load_settings("config.yaml"))
    s.stages.devils_advocate = False
    texts = [FOR, "no json", "no json again", EVID] + [member(p) for p in (0.2, 0.3, 0.25, 0.22)]
    # forensics succeeds, blind base rate fails both attempts
    rec = await pipeline.forecast_question(_bq(), s, FakeLlm(texts), FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    assert "BLIND_FAILED" in rec.guards_fired and rec.blind is None
    assert rec.published and rec.error is None

    texts = ["no json", "no json again", BLIND, EVID] + [member(p) for p in (0.2, 0.3, 0.25, 0.22)]
    rec = await pipeline.forecast_question(_bq(), s, FakeLlm(texts), FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    assert "FORENSICS_FAILED" in rec.guards_fired
    assert rec.forensics is not None and rec.forensics.status_quo_outcome == "unknown"  # the minimal fallback
    assert rec.published and rec.error is None


class JumpLlm(FakeLlm):
    """Books a sudden spend after the Nth call, as a runaway provider bill would."""

    def __init__(self, texts, jump_at, to):
        super().__init__(texts)
        self.jump_at, self.to, self.calls = jump_at, to, 0

    async def complete(self, prompt, model, temperature=0.5, system=None, max_tokens=4000):
        self.calls += 1
        res = await super().complete(prompt, model, temperature, system, max_tokens)
        if self.calls == self.jump_at:
            self.total_cost_usd = self.to
        return res


async def test_roster_is_trimmed_when_the_budget_is_nearly_gone(tmp_path):
    s = _offline(load_settings("config.yaml"))
    assert len(s.models.members) == 4 and s.limits.min_members == 2
    # 0.9 of a $1.00 per-question cap is past the 0.7 trim fraction. Only two member
    # texts are supplied: a third member would pop from an empty list.
    texts = [FOR, BLIND, EVID, member(0.2), member(0.3)]
    llm = JumpLlm(texts, jump_at=3, to=0.9)
    rec = await pipeline.forecast_question(_bq(), s, llm, FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    assert "MEMBERS_TRIMMED_BUDGET" in rec.guards_fired
    assert len(rec.members) == 2 and llm.calls == 5 and llm.texts == []
    assert "DA_SKIPPED_BUDGET" in rec.guards_fired  # 0.9 also trips the DA budget rule
    assert rec.published and rec.error is None


async def test_budget_exhausted_skips_devils_advocate(tmp_path):
    s = _offline(load_settings("config.yaml"))
    texts = [FOR, BLIND, EVID] + [member(p) for p in (0.2, 0.3, 0.25, 0.22)]
    llm = JumpLlm(texts, jump_at=7, to=1.5)  # over the $1.00 per-question cap
    rec = await pipeline.forecast_question(_bq(), s, llm, FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    assert "BUDGET_EXHAUSTED" in rec.guards_fired
    assert rec.aggregate.post_da is None and llm.texts == []  # DA texts were never needed
    assert rec.final.probability == pytest.approx(rec.aggregate.pre_da.probability)
    assert rec.published


async def test_devils_advocate_multiple_choice_move_is_bounded(tmp_path):
    s = _offline(load_settings("config.yaml"))
    texts = [FOR, BLIND_MC, EVID] + [mc_member(a) for a in (0.5, 0.6, 0.55, 0.45)] + [CRIT, REV_MC]
    rec = await pipeline.forecast_question(_mcq(), s, FakeLlm(texts), FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    pre_a, post_a = rec.aggregate.pre_da.options["A"], rec.final.options["A"]
    assert rec.aggregate.post_da is not None
    assert post_a > pre_a  # it did move toward the critique
    assert post_a < 0.8    # but nowhere near the 0.98 the reviser asked for
    assert sum(rec.final.options.values()) == pytest.approx(1.0)
    assert rec.published


async def test_devils_advocate_numeric_move_is_capped_to_a_fraction_of_the_spread(tmp_path):
    s = _offline(load_settings("config.yaml"))
    texts = [FOR, BLIND_NUM, EVID] + [numeric_member(d) for d in (0, 2, -2, 1)] + [CRIT, REV_NUM]
    rec = await pipeline.forecast_question(_nq(), s, FakeLlm(texts), FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    pre = rec.aggregate.pre_da.percentiles
    post = rec.final.percentiles
    assert rec.aggregate.post_da is not None
    cap = s.forecast.da_max_numeric_fraction * (pre[90] - pre[10])
    for k in pre:
        assert abs(post[k] - pre[k]) <= cap + 1e-6, (k, pre[k], post[k], cap)
    assert post[40] > pre[40]      # moved toward the revision
    assert post[40] < 75 - 1e-9    # but not all the way to it
    vals = [post[k] for k in sorted(post)]
    assert all(b > a for a, b in zip(vals, vals[1:]))
    assert rec.published


class CommentFailingPublisher(FakePublisher):
    def publish(self, q, value, comment):
        raise pipeline.CommentPostError("RuntimeError: comment api down")


async def test_comment_failure_still_counts_as_published(tmp_path):
    # The prediction is what scores. If only the comment post fails the record must say
    # published, or the next run re-forecasts a question that already has a forecast.
    s = _offline(load_settings("config.yaml"))
    s.stages.devils_advocate = False
    texts = [FOR, BLIND, EVID] + [member(p) for p in (0.2, 0.3, 0.25, 0.22)]
    rec = await pipeline.forecast_question(_bq(), s, FakeLlm(texts), CommentFailingPublisher(), "2026-09-12", runs_dir=str(tmp_path))
    assert rec.published and "COMMENT_FAILED" in rec.guards_fired and rec.error is None


async def test_comment_footer_shows_the_real_cost(tmp_path):
    s = _offline(load_settings("config.yaml"))
    s.stages.devils_advocate = False
    texts = [FOR, BLIND, EVID] + [member(p) for p in (0.2, 0.3, 0.25, 0.22)]
    llm = FakeLlm(texts)
    rec = await pipeline.forecast_question(_bq(), s, llm, FakePublisher(), "2026-09-12", runs_dir=str(tmp_path))
    assert f"cost=${rec.cost_usd:.2f}" in rec.comment
    assert rec.cost_usd == pytest.approx(llm.total_cost_usd)


# --------------------------------------------------------------------------
# MetaculusPublisher against a recording client (T4)
# --------------------------------------------------------------------------

class RecordingClient:
    def __init__(self, state=QuestionState.OPEN, close_time=None, comment_raises=False):
        self.calls = []
        self.q = SimpleNamespace(state=state, close_time=close_time)
        self.comment_raises = comment_raises

    def get_question_by_post_id(self, post_id, group_question_mode="exclude"):
        self.calls.append(("get", post_id))
        return self.q

    def post_binary_question_prediction(self, question_id, p):
        self.calls.append(("binary", question_id, p))

    def post_multiple_choice_question_prediction(self, question_id, options):
        self.calls.append(("mc", question_id, options))

    def post_numeric_question_prediction(self, question_id, cdf):
        self.calls.append(("numeric", question_id, cdf))

    def post_question_comment(self, post_id, text, is_private=False):
        if self.comment_raises:
            raise RuntimeError("comment api down")
        self.calls.append(("comment", post_id, text, is_private))


def _qs(kind="binary", **kw):
    base = dict(post_id=5, question_id=6, url="https://m/5", title="t", kind=kind, close_time=None, options=None,
                lower_bound=None, upper_bound=None, open_lower=None, open_upper=None, cdf_size=None,
                zero_point=None, unit=None)
    base.update(kw)
    return QuestionSummary(**base)


def test_publisher_posts_binary_then_comment():
    c = RecordingClient()
    pipeline.MetaculusPublisher(c).publish(_qs(), ForecastValue(kind="binary", probability=0.3), "body")
    assert c.calls == [("binary", 6, 0.3), ("comment", 5, "body", True)]


def test_publisher_posts_multiple_choice_dict():
    c = RecordingClient()
    opts = {"A": 0.5, "B": 0.3, "C": 0.2}
    pipeline.MetaculusPublisher(c).publish(_qs("multiple_choice", options=["A", "B", "C"]),
                                           ForecastValue(kind="multiple_choice", options=opts), "body")
    assert c.calls[0] == ("mc", 6, opts)
    assert c.calls[1][0] == "comment"


def test_publisher_posts_numeric_cdf_of_declared_size():
    c = RecordingClient()
    qs = _qs("numeric", lower_bound=0.0, upper_bound=100.0, open_lower=False, open_upper=False, cdf_size=201)
    value = ForecastValue(kind="numeric", percentiles={10: 20.0, 50: 50.0, 90: 80.0})
    pipeline.MetaculusPublisher(c).publish(qs, value, "body")
    kind, qid, cdf = c.calls[0]
    assert kind == "numeric" and qid == 6
    assert len(cdf) == 201 and all(b >= a for a, b in zip(cdf, cdf[1:]))
    assert c.calls[1][0] == "comment"


def test_publisher_comment_failure_raises_comment_post_error():
    c = RecordingClient(comment_raises=True)
    with pytest.raises(pipeline.CommentPostError):
        pipeline.MetaculusPublisher(c).publish(_qs(), ForecastValue(kind="binary", probability=0.3), "body")
    assert c.calls == [("binary", 6, 0.3)]  # the prediction did land


def test_publisher_is_open_reads_state_and_close_time():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    assert pipeline.MetaculusPublisher(RecordingClient(QuestionState.OPEN, future)).is_open(5)
    assert not pipeline.MetaculusPublisher(RecordingClient(QuestionState.CLOSED, future)).is_open(5)
    assert not pipeline.MetaculusPublisher(RecordingClient(QuestionState.OPEN, past)).is_open(5)
    assert pipeline.MetaculusPublisher(RecordingClient(QuestionState.OPEN, None)).is_open(5)


class GroupRecordingClient(RecordingClient):
    """Mimics forecasting-tools on a question-group post: the default lookup raises,
    unpack mode returns one MetaculusQuestion per subquestion."""
    def __init__(self, subs):
        super().__init__()
        self.subs = subs

    def get_question_by_post_id(self, post_id, group_question_mode="exclude"):
        self.calls.append(("get", post_id, group_question_mode))
        if group_question_mode == "exclude":
            raise ValueError("Expected 1 question but got 0. You probably accessed a group question.")
        return list(self.subs)


def test_publisher_is_open_handles_group_subquestions():
    # Live failure 2026-09-13 on post 43322 (a question-group subquestion): the publish gate
    # re-fetched by post id, the library excluded the group, raised, and the question was
    # recorded PIPELINE_ERROR after $0.45 of work. is_open must resolve the subquestion.
    future = datetime.now(timezone.utc) + timedelta(days=1)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    subs = [SimpleNamespace(id_of_question=6, state=QuestionState.OPEN, close_time=future),
            SimpleNamespace(id_of_question=7, state=QuestionState.CLOSED, close_time=past)]
    pub = pipeline.MetaculusPublisher(GroupRecordingClient(subs))
    assert pub.is_open(5, question_id=6)
    assert not pub.is_open(5, question_id=7)
    assert not pub.is_open(5, question_id=99)  # subquestion vanished: do not publish


async def test_timed_out_question_record_carries_a_guard(tmp_path, monkeypatch):
    # asyncio.wait_for cancellation is a BaseException, so it skipped every `except
    # Exception`: the finally wrote a record with guards=[] and error=None, and nothing in
    # the file said the question timed out.
    import asyncio
    from forecasting_tools import BinaryQuestion
    from bot.config import load_settings
    from bot.llm import Llm
    from tests.test_llm import FakeTransport

    async def wedged(*a, **k):
        await asyncio.sleep(30)

    monkeypatch.setattr(pipeline.forensics, "run", wedged)
    s = load_settings("config.yaml")
    q = BinaryQuestion(question_text="t", id_of_post=5, id_of_question=6, page_url="https://m/5", close_time=None)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(pipeline.forecast_question(q, s, Llm(s, FakeTransport()), None, "2026-09-14", str(tmp_path)), timeout=0.05)
    recs = list(tmp_path.glob("**/*.json"))
    assert len(recs) == 1
    body = json.loads(recs[0].read_text(encoding="utf-8"))
    assert "QUESTION_TIMEOUT" in body["guards_fired"]
    assert body["published"] is False


def test_budget_soft_wall_fires_before_hard_timeout():
    from bot.config import load_settings
    from bot.guards import Budget
    s = load_settings("config.yaml")
    b = pipeline.make_budget(s)
    assert b.wall < s.limits.question_wall_clock_s
