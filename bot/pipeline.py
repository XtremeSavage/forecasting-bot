from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Protocol
from forecasting_tools import MetaculusClient, MetaculusQuestion
from forecasting_tools.data_models.questions import QuestionState
from bot import aggregate as agg, comment as comment_mod, records
from bot.config import Settings
from bot.guards import Budget, drop_invalid_members, enough_members, validate_value
from bot.llm import Llm
from bot.models import Aggregate, EvidenceTable, Forensics, ForecastRecord, ForecastValue, MemberForecast, QuestionSummary, StageCost
from bot.stages import base_rate, devils_advocate, evidence, forecast, forensics, research

log = logging.getLogger(__name__)


NUMERIC_KINDS = ("numeric", "discrete", "date")


class CommentPostError(Exception):
    """The prediction posted but the reasoning comment did not.

    Raised so the caller can still mark the record published: the forecast is what
    scores, the comment is commentary, and losing the comment must not make the bot
    think it never forecast (which would make it re-forecast the question next run).
    """


class Publisher(Protocol):
    def is_open(self, post_id: int) -> bool: ...
    def publish(self, q: QuestionSummary, value: ForecastValue, comment: str) -> None: ...


class MetaculusPublisher:
    def __init__(self, client: MetaculusClient) -> None:
        self.c = client

    def is_open(self, post_id: int) -> bool:
        q = self.c.get_question_by_post_id(post_id)
        now = datetime.now(timezone.utc)
        return q.state == QuestionState.OPEN and (q.close_time is None or q.close_time > now)

    def publish(self, q: QuestionSummary, value: ForecastValue, comment: str) -> None:
        if value.kind == "binary":
            self.c.post_binary_question_prediction(q.question_id, value.probability)
        elif value.kind == "multiple_choice":
            self.c.post_multiple_choice_question_prediction(q.question_id, value.options)
        else:
            self.c.post_numeric_question_prediction(q.question_id, agg.percentiles_to_cdf(value.percentiles, q))
        try:
            self.c.post_question_comment(q.post_id, comment, is_private=True)
        except Exception as e:  # noqa: BLE001
            raise CommentPostError(f"{type(e).__name__}: {e}") from e


def _stage(rec: ForecastRecord, name: str, model: str, cost: float, t0: float) -> None:
    rec.stage_costs.append(StageCost(stage=name, model=model, cost_usd=cost, seconds=time.monotonic() - t0))
    rec.cost_usd += cost


async def forecast_question(q: MetaculusQuestion, settings: Settings, llm: Llm, publisher: Publisher | None, today: str, runs_dir: str = "runs") -> ForecastRecord:
    qs = records.question_summary(q)
    rec = ForecastRecord(question=qs, run_ts=datetime.now(timezone.utc).isoformat(), flags=settings.stages.model_dump())
    budget = Budget(settings.limits.question_wall_clock_s, settings.limits.per_question_usd)
    desc, crit, fine = q.background_info or "", q.resolution_criteria or "", q.fine_print or ""
    cost0 = getattr(llm, "total_cost_usd", 0.0)
    fb0 = getattr(llm, "fallback_used", False)

    def spent() -> float:
        return max(rec.cost_usd, getattr(llm, "total_cost_usd", 0.0) - cost0)

    try:
        # Date questions are not supported: the whole numeric path works in floats and the
        # publisher would post a CDF built from timestamps, which is not what Metaculus
        # expects for a date question. Bail out before spending anything on one.
        if qs.kind == "date":
            rec.guards_fired.append("SKIP_DATE_UNSUPPORTED")
            return rec
        # Stages 1-3 are each optional context for the forecast, not preconditions for it.
        # A stage that blows up degrades the forecast; it must not abort the question, so
        # each falls back to exactly what the pipeline uses when the stage flag is off.
        minimal_forensics = Forensics(resolution_statement=crit[:1500], status_quo_outcome="unknown", search_queries=[qs.title])
        # Stage 1
        f = minimal_forensics
        if settings.stages.forensics:
            t0 = time.monotonic()
            try:
                f, res = await forensics.run(llm, settings, qs, desc, crit, fine, today)
                _stage(rec, "forensics", res.model, res.cost_usd, t0)
            except Exception as e:  # noqa: BLE001
                log.warning("forensics failed on %s: %s", qs.url, e)
                rec.guards_fired.append("FORENSICS_FAILED")
                f = minimal_forensics
        rec.forensics = f
        # Stage 2
        blind = None
        if settings.stages.blind_base_rate:
            t0 = time.monotonic()
            try:
                blind, res = await base_rate.run(llm, settings, qs, desc, crit, f, today)
                _stage(rec, "blind_base_rate", res.model, res.cost_usd, t0)
            except Exception as e:  # noqa: BLE001
                log.warning("blind base rate failed on %s: %s", qs.url, e)
                rec.guards_fired.append("BLIND_FAILED")
                blind = None
        rec.blind = blind
        # Stage 3
        ev = None
        if settings.stages.evidence_table:
            try:
                t0 = time.monotonic()
                bundle, rcost = await research.run(llm, settings, f, crit, desc)
                rec.research = bundle
                _stage(rec, "research", settings.models.web_search, rcost, t0)
                t0 = time.monotonic()
                ev, res = await evidence.run(llm, settings, qs, f, bundle, today)
                _stage(rec, "evidence_table", res.model, res.cost_usd, t0)
            except Exception as e:  # noqa: BLE001
                log.warning("research/evidence failed on %s: %s", qs.url, e)
                rec.guards_fired.append("EVIDENCE_FAILED")
                ev = None
            if rec.research is not None and "NO_RESEARCH" in rec.research.diagnostics:
                rec.guards_fired.append("NO_RESEARCH")
        rec.evidence = ev
        # Stage 4
        if not settings.stages.ach_forecast:
            rec.guards_fired.append("SKIP_ACH_OFF")
            return rec
        t0 = time.monotonic()

        async def one(m):
            try:
                return await forecast.run_member(llm, settings, m, qs, desc, crit, fine, f, blind, ev, today)
            except Exception as e:  # noqa: BLE001
                return MemberForecast(name=m.name, model=m.model, forecast=ForecastValue(kind=qs.kind), reasoning="", dropped_reason=f"{type(e).__name__}: {e}")

        # The member fan-out is the single most expensive step. If the earlier stages
        # already ate most of the per-question budget, run the minimum viable ensemble
        # instead of the full roster rather than blowing through the cap.
        roster = list(settings.models.members)
        if spent() >= settings.limits.per_question_usd * settings.limits.da_skip_at_budget_fraction:
            roster = roster[: settings.limits.min_members]
            rec.guards_fired.append("MEMBERS_TRIMMED_BUDGET")
        members: list[MemberForecast] = list(await asyncio.gather(*(one(m) for m in roster)))
        rec.members = members
        _stage(rec, "forecast_members", "ensemble", sum(m.cost_usd for m in members), t0)
        survivors = drop_invalid_members([m for m in members if m.dropped_reason is None], qs)
        if not enough_members(survivors, settings.limits.min_members):
            rec.guards_fired.append("SKIP_MIN_MEMBERS")
            return rec
        pre = agg.aggregate([m.forecast for m in survivors], qs, settings.forecast)
        rec.aggregate = Aggregate(pre_da=pre, method="logit_median" if qs.kind == "binary" else ("option_median" if qs.kind == "multiple_choice" else "cdf_pointwise_median"))
        # Every member can be individually valid and the aggregate still not be: the
        # pointwise-median round trip can flatten a distribution. Check the aggregate the
        # same way, including a trial CDF build, before anything is posted.
        problems = validate_value(pre, qs)
        if not problems and qs.kind in NUMERIC_KINDS:
            try:
                agg.percentiles_to_cdf(pre.percentiles, qs)
            except Exception as e:  # noqa: BLE001
                problems = [f"aggregate distribution cannot be built: {type(e).__name__}: {e}"]
        if problems:
            log.warning("aggregate invalid on %s: %s", qs.url, problems)
            rec.guards_fired.append("AGGREGATE_INVALID")
            return rec
        final = pre
        # Stage 5
        exhausted = budget.exhausted(spent())
        if exhausted:
            rec.guards_fired.append("BUDGET_EXHAUSTED")
        if settings.stages.devils_advocate:
            if exhausted:
                pass  # BUDGET_EXHAUSTED already recorded; publish the pre-DA aggregate
            elif budget.should_skip_da(spent(), settings.limits.da_skip_at_budget_fraction):
                rec.guards_fired.append("DA_SKIPPED_BUDGET")
            else:
                t0 = time.monotonic()
                try:
                    revised, critique, dcost = await devils_advocate.run(llm, settings, qs, f, ev or EvidenceTable(), pre, today)
                    _stage(rec, "devils_advocate", settings.models.forecast_tier, dcost, t0)
                    rec.aggregate.da_critique = critique
                    if qs.kind == "binary":
                        p = agg.bounded_logit_shift(pre.probability, revised.probability, settings.forecast.da_max_logit_shift)
                        final = ForecastValue(kind="binary", probability=agg.aggregate_binary([p], settings.forecast.p_min, settings.forecast.p_max))
                        rec.aggregate.post_da = final
                    elif validate_value(revised, qs) == []:
                        # Binary revisions are bounded in logit space; bound the other
                        # kinds too, or one confident critique rewrites the ensemble.
                        if qs.kind == "multiple_choice":
                            shifted = {o: agg.bounded_logit_shift(pre.options[o], revised.options[o], settings.forecast.da_max_logit_shift) for o in qs.options}
                            cand = ForecastValue(kind="multiple_choice", options=agg.aggregate_mc([shifted], qs.options, settings.forecast.mc_floor))
                        else:
                            cand = ForecastValue(kind=qs.kind, percentiles=agg.bounded_percentile_shift(pre.percentiles, revised.percentiles, settings.forecast.da_max_numeric_fraction))
                        if validate_value(cand, qs) == []:
                            final = cand
                            rec.aggregate.post_da = final
                        else:
                            rec.guards_fired.append("DA_REVISION_INVALID")
                    else:
                        rec.guards_fired.append("DA_REVISION_INVALID")
                except Exception as e:  # noqa: BLE001
                    rec.guards_fired.append("DA_FAILED")
                    rec.aggregate.da_critique = f"DA failed: {type(e).__name__}: {e}"
                    final = pre
        rec.final = final
        rec.cost_usd = spent()  # so the comment footer shows the real spend, not a partial
        rec.comment = comment_mod.build(rec, settings.comment.max_chars)
        # Publish gate
        if publisher is None:
            return rec
        if not publisher.is_open(qs.post_id):
            rec.guards_fired.append("PUBLISH_SKIPPED_CLOSED")
            return rec
        try:
            publisher.publish(qs, final, rec.comment)
        except CommentPostError as e:
            log.warning("comment post failed on %s (prediction is live): %s", qs.url, e)
            rec.published = True
            rec.guards_fired.append("COMMENT_FAILED")
            return rec
        rec.published = True
        return rec
    except Exception as e:  # noqa: BLE001
        log.exception("pipeline error on %s", qs.url)
        rec.error = f"{type(e).__name__}: {e}"
        rec.guards_fired.append("PIPELINE_ERROR")
        return rec
    finally:
        rec.cost_usd = spent()
        if llm is not None and getattr(llm, "fallback_used", False) and not fb0:
            rec.guards_fired.append("PROVIDER_FALLBACK")
        records.write(rec, runs_dir)
