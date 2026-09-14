from __future__ import annotations
import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
import dotenv
from forecasting_tools import (BinaryQuestion, DiscreteQuestion, MetaculusClient, MetaculusQuestion,
                               MultipleChoiceQuestion, NumericQuestion)
from bot import records
from bot.config import load_settings
from bot.guards import season_spent
from bot.llm import Llm
from bot.pipeline import MetaculusPublisher, forecast_question

log = logging.getLogger("run")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="XtremeSavageForecast bot")
    p.add_argument("--mode", choices=["tournament", "cup", "test", "dry"], default="tournament")
    p.add_argument("--tournament", default=None, help="tournament id or slug for dry mode")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--runs-dir", default="runs")
    return p.parse_args(argv)


SUPPORTED_TYPES = (BinaryQuestion, MultipleChoiceQuestion, NumericQuestion, DiscreteQuestion)


def effective_limit(cli_limit: int | None, default: int) -> int:
    # `--limit 0` must mean zero, not "unset": the workflow forwards the dispatch input
    # verbatim, and 0 falling through to the default would publish 15 live questions.
    return default if cli_limit is None else cli_limit


def select_questions(questions: list[MetaculusQuestion], max_n: int, runs_dir: str) -> list[MetaculusQuestion]:
    far = datetime.max.replace(tzinfo=timezone.utc)
    keep: list[MetaculusQuestion] = []
    seen: set[int | None] = set()
    for q in questions:
        # Conditional and date questions would crash question_summary before any record
        # exists (and be re-selected every run); drop them here with a log line instead.
        if not isinstance(q, SUPPORTED_TYPES):
            log.info("skipping unsupported %s post %s", type(q).__name__, getattr(q, "id_of_post", "?"))
            continue
        # The same question can appear in two targets (Fall and MiniBench share posts).
        if q.id_of_question in seen:
            continue
        seen.add(q.id_of_question)
        if q.already_forecasted or records.already_forecasted_locally(q.id_of_post, q.id_of_question, runs_dir):
            continue
        keep.append(q)
    keep.sort(key=lambda q: q.close_time or far)
    return keep[:max_n]


async def _run(args) -> int:
    s = load_settings(args.config)
    spent = season_spent(args.runs_dir)
    if spent >= s.limits.season_usd:
        log.error("SEASON_CAP reached: spent $%.2f", spent)
        return 2
    client = MetaculusClient()
    targets = {"tournament": [s.tournaments.fall, s.tournaments.minibench], "cup": [s.tournaments.cup],
               "test": [s.tournaments.test], "dry": [args.tournament or s.tournaments.test]}[args.mode]
    publisher = None if args.mode == "dry" else MetaculusPublisher(client)
    questions: list[MetaculusQuestion] = []
    for t in targets:
        questions += client.get_all_open_questions_from_tournament(t)
    questions = select_questions(questions, effective_limit(args.limit, s.limits.max_questions_per_run), args.runs_dir)
    log.info("forecasting %d questions (mode=%s)", len(questions), args.mode)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sem = asyncio.Semaphore(s.limits.max_concurrent_questions)
    guards = 0

    async def one(q):
        nonlocal guards
        async with sem:
            try:
                # Hard per-question wall clock. Without it a single wedged provider call
                # (or a pathological numeric distribution) blocks the whole run, and the
                # run has a fixed window before the question closes.
                rec = await asyncio.wait_for(
                    forecast_question(q, s, Llm(s), publisher, today, args.runs_dir),
                    timeout=s.limits.question_wall_clock_s,
                )
            except asyncio.TimeoutError:
                log.error("QUESTION_TIMEOUT after %ss for post %s", s.limits.question_wall_clock_s, getattr(q, "id_of_post", "?"))
                guards += 1
                return
            except Exception:
                log.exception("forecast_question failed for post %s", getattr(q, "id_of_post", "?"))
                guards += 1
                return
            guards += len(rec.guards_fired)
            log.info("%s -> published=%s final=%s guards=%s cost=$%.2f", rec.question.url, rec.published, rec.final, rec.guards_fired, rec.cost_usd)

    await asyncio.gather(*(one(q) for q in questions))
    return 1 if guards else 0


def main(argv=None) -> int:
    dotenv.load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return asyncio.run(_run(parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
