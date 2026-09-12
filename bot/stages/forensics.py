from __future__ import annotations
from bot.llm import Llm, LlmResult
from bot.config import Settings
from bot.models import Forensics, QuestionSummary
from bot.stages.common import CONVENTION, question_block

SYSTEM = "You are a meticulous intelligence analyst doing resolution forensics on a forecasting question. You do not forecast here."


def build_prompt(q: QuestionSummary, description: str, criteria: str, fine_print: str, today: str) -> str:
    return f"""{question_block(q, description, criteria, fine_print, today)}
{CONVENTION}

Do resolution forensics before any research happens:
1. State in one precise paragraph exactly what makes this resolve each way (or each option / each value range). Quote the operative phrases.
2. Name the status quo outcome: what resolves if nothing changes between today and close.
3. List the key dates (deadline, snapshot date, data release dates).
4. List traps: ambiguous phrases, 'before' vs 'on', time zones, which source is authoritative, annulment conditions, partial events that do NOT count.
5. Could this already be resolved as of today? Say true only if the background or criteria themselves indicate it.
6. Write 3 to 5 search queries that would find the decisive evidence. Prefer the authoritative resolution source and recent news.
7. List things that superficially look like a Yes/qualifying outcome but do not count.

Finish with a fenced JSON block exactly matching this schema:
```json
{{"resolution_statement": "...", "status_quo_outcome": "...", "key_dates": ["..."], "traps": ["..."], "possibly_already_resolved": false, "already_resolved_reason": "", "search_queries": ["..."], "things_that_do_not_count": ["..."]}}
```"""


async def run(llm: Llm, settings: Settings, q: QuestionSummary, description: str, criteria: str, fine_print: str, today: str) -> tuple[Forensics, LlmResult]:
    prompt = build_prompt(q, description, criteria, fine_print, today)
    return await llm.complete_json(prompt, settings.models.forecast_tier, Forensics, temperature=0.2, system=SYSTEM)
