# Forecasting Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a guarded, measurable Metaculus forecasting bot with five intelligence-tradecraft stages, plus an unmodified template control bot, both running on GitHub Actions before the Sep 21 warmup MiniBench.

**Architecture:** Our own thin pipeline (`bot/`) uses forecasting-tools only as the Metaculus API layer. Each tradecraft stage is a pure function pair (`build_prompt` / `parse`) with an async `run` wrapper, gated by a config flag. LLM calls go through one wrapper (`bot/llm.py`) that talks to OpenRouter via the `openai` SDK with exact per-call cost from OpenRouter's usage field, falling back to Anthropic direct. Every question produces one JSON record in `runs/` that the workflow commits back to the repo.

**Tech Stack:** Python 3.11 (Actions) / 3.12 (local venv at `.venv`), Poetry, forecasting-tools 0.3.1, openai SDK, anthropic SDK, httpx, trafilatura, pydantic v2, pytest, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-09-11-forecasting-bot-design.md`

**Status (2026-09-12):** All 14 tasks implemented and reviewed on branch `build/v1`. Deferred by design: Task 2 Step 7 and Task 12 Step 7 live triggers, Task 11 Step 5 paid dry run, Task 13 Step 4 community-prediction discovery, Task 14 Pages enablement. Rulings and per-task review outcomes are in `docs/superpowers/ledger-2026-09-12.md`. See `docs/HANDOFF.md`.

## Global Constraints

- Python `^3.11`. Local commands use `.venv/Scripts/python.exe` (Windows). Actions use Python 3.11 + Poetry.
- forecasting-tools pinned `0.3.1`. Only `MetaculusClient`, question classes, `NumericDistribution`, `Percentile`, `AskNewsSearcher` are imported from it.
- Budget: `$1.00` per question, `$500` per season, enforced in code.
- Binary clamp default `[0.01, 0.99]`. Metaculus hard limit is `[0.001, 0.999]`.
- Numeric CDF: 201 points for numeric, `question.cdf_size` for discrete; monotone; step >= 5e-05.
- Tournament IDs: Fall `33121` / `fall-futureeval-2026`; MiniBench `minibench`; testing area `32977` / `bot-testing-area`; Metaculus Cup `33108`.
- Model roster (verified on OpenRouter 2026-09-11): forecast tier `openai/gpt-5.4`; members `openai/gpt-5.4` (t=0.3), `openai/gpt-5.4` (t=0.8), `anthropic/claude-sonnet-4.6`, `x-ai/grok-4.6`; cheap tier `openai/gpt-5.4-mini`; web search `openai/gpt-5.4-mini:online`.
- Secrets never in code. `.env` is gitignored. Actions secrets: `METACULUS_TOKEN`, `METACULUS_TOKEN_CONTROL`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `ASKNEWS_CLIENT_ID`, `ASKNEWS_SECRET`.
- Commit after every task. Commit message format: `type: summary` plus the attribution trailer given in the session.
- Prompts state the Metaculus convention: assume the event has NOT happened unless evidence shows it has.

## File Structure

```
forecasting-bot/
  pyproject.toml            Poetry project; deps listed in Task 1
  config.yaml               flags, roster, clamps, caps (Task 1)
  .env.template             (Task 1)
  control_bot.py            template main.py verbatim (Task 2)
  bot_helpers.py            template helper verbatim (Task 2)
  run.py                    our CLI entrypoint (Task 11)
  scores.py                 score joiner (Task 13)
  bot/__init__.py
  bot/config.py             Settings dataclass + loader (Task 1)
  bot/models.py             all pydantic records (Task 3)
  bot/llm.py                OpenRouter/Anthropic wrapper + cost (Task 4)
  bot/aggregate.py          logit median, MC, CDF median (Task 5)
  bot/guards.py             publish guards (Task 6)
  bot/stages/__init__.py
  bot/stages/forensics.py   stage 1 (Task 7)
  bot/stages/base_rate.py   stage 2 (Task 7)
  bot/stages/evidence.py    stage 3b (Task 7)
  bot/stages/forecast.py    stage 4 (Task 7)
  bot/stages/devils_advocate.py  stage 5 (Task 7)
  bot/stages/research.py    stage 3a providers (Task 8)
  bot/comment.py            comment builder (Task 9)
  bot/records.py            run record writer (Task 9)
  bot/pipeline.py           orchestration (Task 10)
  runs/.gitkeep
  tests/                    one test file per module
  tests/fixtures/           recorded stage outputs
  .github/workflows/{control_bot,main_bot,cup,test}.yaml  (Tasks 2, 12)
  docs/dashboard/index.html (Task 14)
```

---

### Task 1: Project scaffold and config

**Files:**
- Create: `pyproject.toml`, `config.yaml`, `.env.template`, `bot/__init__.py`, `bot/config.py`, `runs/.gitkeep`, `tests/__init__.py`, `tests/test_config.py`
- Modify: `.gitignore` (add `runs/*.tmp`, `.pytest_cache/`, `*.egg-info/`)

**Interfaces:**
- Produces: `bot.config.Settings` (pydantic model) with fields below; `bot.config.load_settings(path: str = "config.yaml") -> Settings`; env overrides via `FB_` prefix are NOT needed in v1 (keep simple).

- [ ] **Step 1: Write pyproject.toml**

```toml
[tool.poetry]
name = "forecasting-bot"
version = "0.1.0"
description = "Metaculus FutureEval bot with intelligence-tradecraft stages"
authors = ["XtremeSavageXD"]
readme = "README.md"
package-mode = false

[tool.poetry.dependencies]
python = "^3.11"
forecasting-tools = "0.3.1"
openai = "^2.0.0"
anthropic = "^0.60.0"
httpx = "^0.28.0"
trafilatura = "^2.0.0"
pydantic = "^2.7"
pyyaml = "^6.0"
python-dotenv = "^1.0.1"
numpy = "^2.3.0"
asknews = "^0.13.11"

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"
pytest-asyncio = "^0.24"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

- [ ] **Step 2: Write config.yaml**

```yaml
stages:
  forensics: true
  blind_base_rate: true
  evidence_table: true
  ach_forecast: true
  devils_advocate: true

models:
  forecast_tier: openai/gpt-5.4
  cheap_tier: openai/gpt-5.4-mini
  web_search: openai/gpt-5.4-mini:online
  anthropic_fallback: claude-sonnet-4-6
  members:
    - {name: gpt54_a, model: openai/gpt-5.4, temperature: 0.3}
    - {name: gpt54_b, model: openai/gpt-5.4, temperature: 0.8}
    - {name: sonnet46, model: anthropic/claude-sonnet-4.6, temperature: 0.5}
    - {name: grok46, model: x-ai/grok-4.6, temperature: 0.5}

limits:
  per_call_usd: 0.40
  per_question_usd: 1.00
  season_usd: 500.0
  question_wall_clock_s: 600
  da_skip_at_budget_fraction: 0.7
  min_members: 2
  max_questions_per_run: 15
  max_concurrent_questions: 3

forecast:
  p_min: 0.01
  p_max: 0.99
  mc_floor: 0.01
  da_max_logit_shift: 0.5
  numeric_percentiles: [5, 10, 20, 40, 60, 80, 90, 95]

research:
  asknews_enabled: true
  web_search_enabled: true
  resolution_fetch_enabled: true
  max_queries: 5
  provider_timeout_s: 90
  source_text_max_chars: 6000

tournaments:
  fall: 33121
  minibench: minibench
  cup: 33108
  test: bot-testing-area

comment:
  max_chars: 3000
```

- [ ] **Step 3: Write .env.template**

```
METACULUS_TOKEN=REPLACE_ME
METACULUS_TOKEN_CONTROL=REPLACE_ME
OPENROUTER_API_KEY=REPLACE_ME
ANTHROPIC_API_KEY=REPLACE_ME
ASKNEWS_CLIENT_ID=REPLACE_ME
ASKNEWS_SECRET=REPLACE_ME
```

- [ ] **Step 4: Write the failing test**

`tests/test_config.py`:
```python
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
```

- [ ] **Step 5: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot'`

- [ ] **Step 6: Write bot/config.py**

```python
from __future__ import annotations
from pathlib import Path
import yaml
from pydantic import BaseModel


class StageFlags(BaseModel):
    forensics: bool = True
    blind_base_rate: bool = True
    evidence_table: bool = True
    ach_forecast: bool = True
    devils_advocate: bool = True


class Member(BaseModel):
    name: str
    model: str
    temperature: float = 0.5


class Models(BaseModel):
    forecast_tier: str
    cheap_tier: str
    web_search: str
    anthropic_fallback: str
    members: list[Member]


class Limits(BaseModel):
    per_call_usd: float = 0.40
    per_question_usd: float = 1.0
    season_usd: float = 500.0
    question_wall_clock_s: int = 600
    da_skip_at_budget_fraction: float = 0.7
    min_members: int = 2
    max_questions_per_run: int = 15
    max_concurrent_questions: int = 3


class ForecastCfg(BaseModel):
    p_min: float = 0.01
    p_max: float = 0.99
    mc_floor: float = 0.01
    da_max_logit_shift: float = 0.5
    numeric_percentiles: list[int] = [5, 10, 20, 40, 60, 80, 90, 95]


class ResearchCfg(BaseModel):
    asknews_enabled: bool = True
    web_search_enabled: bool = True
    resolution_fetch_enabled: bool = True
    max_queries: int = 5
    provider_timeout_s: int = 90
    source_text_max_chars: int = 6000


class Tournaments(BaseModel):
    fall: int | str
    minibench: int | str
    cup: int | str
    test: int | str


class CommentCfg(BaseModel):
    max_chars: int = 3000


class Settings(BaseModel):
    stages: StageFlags
    models: Models
    limits: Limits
    forecast: ForecastCfg
    research: ResearchCfg
    tournaments: Tournaments
    comment: CommentCfg


def load_settings(path: str = "config.yaml") -> Settings:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Settings.model_validate(data)
```

- [ ] **Step 7: Install deps into the venv and run tests**

Run: `.venv/Scripts/python.exe -m pip install pyyaml pytest pytest-asyncio openai anthropic httpx trafilatura` then `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: 2 PASSED

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml config.yaml .env.template bot/ tests/ runs/.gitkeep .gitignore
git commit -m "feat: project scaffold and typed config"
```

---

### Task 2: Control bot (unmodified template) and its workflow

**Files:**
- Create: `control_bot.py` (copy of template `main.py`), `bot_helpers.py` (copy of template), `.github/workflows/control_bot.yaml`, `.github/workflows/control_cup.yaml`
- Source: template tarball already extracted at `%TEMP%\metac-bot-template-main\` (re-download with `curl -L -o mbt.tgz https://codeload.github.com/Metaculus/metac-bot-template/tar.gz/main && tar xzf mbt.tgz` if missing)

**Interfaces:**
- Produces: nothing importable. `control_bot.py --mode {tournament,metaculus_cup,test_questions}` runs the stock template under whatever `METACULUS_TOKEN` is in env.

- [ ] **Step 1: Copy the two files verbatim**

```bash
cp "$TEMP/metac-bot-template-main/main.py" control_bot.py
cp "$TEMP/metac-bot-template-main/bot_helpers.py" bot_helpers.py
```

Do not edit either file. The only allowed change is none. The workflow maps the control token into `METACULUS_TOKEN`.

- [ ] **Step 2: Verify it imports and parses args**

Run: `.venv/Scripts/python.exe control_bot.py --help`
Expected: usage text listing `--mode {tournament,metaculus_cup,test_questions}`. If `bot_helpers.check_environment` complains about missing keys at `--help`, that is fine; `--help` exits before it.

- [ ] **Step 3: Write .github/workflows/control_bot.yaml**

```yaml
name: Control bot (template) on tournament

on:
  workflow_dispatch:
    inputs:
      mode:
        description: "tournament | metaculus_cup | test_questions"
        default: "test_questions"
  schedule:
    - cron: "9,29,49 * * * *"

concurrency:
  group: ${{ github.workflow }}
  cancel-in-progress: false

jobs:
  forecast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: snok/install-poetry@v1
        with:
          virtualenvs-create: true
          virtualenvs-in-project: true
      - run: poetry install --no-interaction --no-root
      - name: Run control bot
        run: poetry run python control_bot.py --mode ${{ github.event.inputs.mode || 'tournament' }}
        env:
          METACULUS_TOKEN: ${{ secrets.METACULUS_TOKEN_CONTROL }}
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          ASKNEWS_CLIENT_ID: ${{ secrets.ASKNEWS_CLIENT_ID }}
          ASKNEWS_SECRET: ${{ secrets.ASKNEWS_SECRET }}
```

- [ ] **Step 4: Write .github/workflows/control_cup.yaml**

Same as above with `name: Control bot on Metaculus Cup`, cron `"0 1 */2 * *"`, no inputs, and the run line `poetry run python control_bot.py --mode metaculus_cup`.

- [ ] **Step 5: Generate poetry.lock so Actions can install**

Run: `poetry lock` (install Poetry first if missing: `.venv/Scripts/python.exe -m pip install poetry`, then `.venv/Scripts/poetry.exe lock`).
Expected: `poetry.lock` created without errors.

- [ ] **Step 6: Commit**

```bash
git add control_bot.py bot_helpers.py .github/workflows/control_bot.yaml .github/workflows/control_cup.yaml poetry.lock
git commit -m "feat: add unmodified template as control bot with workflows"
```

- [ ] **Step 7: Live smoke test (needs XtremeSavageXD's control token in GitHub secrets)**

After the repo is on GitHub with `METACULUS_TOKEN_CONTROL`, `OPENROUTER_API_KEY`, and AskNews secrets set: trigger `Control bot (template) on tournament` with mode `test_questions` from the Actions tab. Expected: green run, forecasts visible on the XtremeSavageForecast-v2 profile for bot-testing-area questions. This is the first thing that spends money; confirm with XtremeSavageXD before triggering.

---

### Task 3: Typed records (bot/models.py)

**Files:**
- Create: `bot/models.py`, `tests/test_models.py`

**Interfaces:**
- Produces every record type used by later tasks. Exact definitions below; later tasks import these names.

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
import json
from bot.models import (
    ForecastValue, Forensics, BlindEstimate, Evidence, EvidenceTable,
    MemberForecast, Aggregate, ForecastRecord, QuestionSummary,
)


def test_forecast_value_kinds():
    b = ForecastValue(kind="binary", probability=0.3)
    m = ForecastValue(kind="multiple_choice", options={"A": 0.7, "B": 0.3})
    n = ForecastValue(kind="numeric", percentiles={10: 1.0, 50: 5.0, 90: 9.0})
    assert b.probability == 0.3 and m.options["A"] == 0.7 and n.percentiles[50] == 5.0


def test_record_roundtrip():
    q = QuestionSummary(post_id=1, question_id=2, url="u", title="t", kind="binary",
                        close_time="2026-09-30T00:00:00+00:00", options=None,
                        lower_bound=None, upper_bound=None, open_lower=None, open_upper=None,
                        cdf_size=None, zero_point=None, unit=None)
    rec = ForecastRecord(question=q, run_ts="2026-09-12T00:00:00+00:00", flags={"forensics": True},
                         members=[MemberForecast(name="a", model="m", forecast=ForecastValue(kind="binary", probability=0.4),
                                                 reasoning="r", stated_number=0.4, cost_usd=0.01)],
                         aggregate=Aggregate(pre_da=ForecastValue(kind="binary", probability=0.4), post_da=None, method="logit_median"),
                         cost_usd=0.02, guards_fired=[], published=False)
    s = rec.model_dump_json()
    back = ForecastRecord.model_validate_json(s)
    assert back.members[0].forecast.probability == 0.4
    assert json.loads(s)["question"]["post_id"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.models'`

- [ ] **Step 3: Write bot/models.py**

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

Kind = Literal["binary", "multiple_choice", "numeric", "date", "discrete"]


class ForecastValue(BaseModel):
    kind: Kind
    probability: float | None = None                 # binary
    options: dict[str, float] | None = None          # multiple_choice
    percentiles: dict[int, float] | None = None      # numeric/discrete/date: percentile -> value


class QuestionSummary(BaseModel):
    post_id: int
    question_id: int
    url: str
    title: str
    kind: Kind
    close_time: str | None
    options: list[str] | None
    lower_bound: float | None
    upper_bound: float | None
    open_lower: bool | None
    open_upper: bool | None
    cdf_size: int | None
    zero_point: float | None
    unit: str | None


class Forensics(BaseModel):
    resolution_statement: str
    status_quo_outcome: str
    key_dates: list[str] = []
    traps: list[str] = []
    possibly_already_resolved: bool = False
    already_resolved_reason: str = ""
    search_queries: list[str] = []
    things_that_do_not_count: list[str] = []


class BlindEstimate(BaseModel):
    reference_class: str
    base_rate_reasoning: str
    forecast: ForecastValue


class RawSource(BaseModel):
    provider: str
    url: str | None = None
    title: str | None = None
    published: str | None = None
    text: str


class ResearchBundle(BaseModel):
    sources: list[RawSource] = []
    diagnostics: dict[str, str] = {}


class Evidence(BaseModel):
    claim: str
    source: str
    date: str | None = None
    reliability: Literal["A", "B", "C", "D", "E", "F"]
    credibility: int = Field(ge=1, le=6)
    supports: str            # outcome label, or "context"
    note: str = ""


class EvidenceTable(BaseModel):
    items: list[Evidence] = []
    already_resolved_signal: str = ""


class MemberForecast(BaseModel):
    name: str
    model: str
    forecast: ForecastValue
    reasoning: str
    stated_number: float | None = None
    cost_usd: float = 0.0
    dropped_reason: str | None = None


class Aggregate(BaseModel):
    pre_da: ForecastValue
    post_da: ForecastValue | None = None
    method: str
    da_critique: str | None = None


class StageCost(BaseModel):
    stage: str
    model: str
    cost_usd: float
    seconds: float


class ForecastRecord(BaseModel):
    question: QuestionSummary
    run_ts: str
    flags: dict[str, bool]
    forensics: Forensics | None = None
    blind: BlindEstimate | None = None
    research: ResearchBundle | None = None
    evidence: EvidenceTable | None = None
    members: list[MemberForecast] = []
    aggregate: Aggregate | None = None
    final: ForecastValue | None = None
    comment: str | None = None
    stage_costs: list[StageCost] = []
    cost_usd: float = 0.0
    guards_fired: list[str] = []
    published: bool = False
    error: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add bot/models.py tests/test_models.py
git commit -m "feat: typed pipeline records"
```

---
### Task 4: LLM wrapper with exact cost (bot/llm.py)

**Files:**
- Create: `bot/llm.py`, `tests/test_llm.py`

**Interfaces:**
- Consumes: `bot.config.Settings`.
- Produces:
  - `class LlmResult(BaseModel)`: `text: str`, `model: str`, `cost_usd: float`, `prompt_tokens: int`, `completion_tokens: int`, `provider: Literal["openrouter","anthropic"]`.
  - `class Llm`: `__init__(self, settings: Settings, transport: Transport | None = None)`; `async complete(self, prompt: str, model: str, temperature: float = 0.5, system: str | None = None, max_tokens: int = 4000) -> LlmResult`; `extract_json(text: str) -> dict` (module-level function); `async complete_json(self, prompt, model, out_type: type[T], temperature=0.5, retries: int = 1) -> tuple[T, LlmResult]`.
  - `class Transport` protocol: `async openrouter(model, messages, temperature, max_tokens) -> dict` and `async anthropic(model, messages, temperature, max_tokens) -> dict`. Real implementation `HttpTransport`; tests inject `FakeTransport`.
  - Exceptions: `LlmError(Exception)`, `CostCeilingError(LlmError)`.

Design notes: OpenRouter returns `usage.cost` when the request body includes `"usage": {"include": true}`. The `openai` SDK passes that via `extra_body`. Anthropic cost is computed from tokens with a small price table (Sonnet 4.6: $3/$15 per million). Per-call ceiling is checked *after* the call against actual cost and raises `CostCeilingError` so the caller can drop the member; before the call we cannot know cost, so we also estimate from prompt length (`len(prompt)/4 * input_price + max_tokens * output_price`) and refuse calls whose estimate exceeds twice the ceiling.

- [ ] **Step 1: Write the failing tests**

`tests/test_llm.py`:
```python
import pytest
from pydantic import BaseModel
from bot.config import load_settings
from bot.llm import Llm, extract_json, LlmError, CostCeilingError


class FakeTransport:
    def __init__(self, replies=None, fail_openrouter=False):
        self.replies = list(replies or [])
        self.fail_openrouter = fail_openrouter
        self.calls = []

    async def openrouter(self, model, messages, temperature, max_tokens):
        self.calls.append(("openrouter", model))
        if self.fail_openrouter:
            raise RuntimeError("openrouter down")
        text = self.replies.pop(0) if self.replies else "ok"
        return {"text": text, "prompt_tokens": 100, "completion_tokens": 50, "cost": 0.0012}

    async def anthropic(self, model, messages, temperature, max_tokens):
        self.calls.append(("anthropic", model))
        text = self.replies.pop(0) if self.replies else "ok"
        return {"text": text, "prompt_tokens": 100, "completion_tokens": 50, "cost": None}


class Out(BaseModel):
    a: int
    b: str


def test_extract_json_fenced_and_bare():
    assert extract_json('blah ```json\n{"a": 1}\n``` more') == {"a": 1}
    assert extract_json('prefix {"a": 2, "b": "x"} suffix') == {"a": 2, "b": "x"}
    with pytest.raises(LlmError):
        extract_json("no json here")


async def test_complete_uses_openrouter_cost():
    s = load_settings("config.yaml")
    t = FakeTransport(replies=["hello"])
    llm = Llm(s, transport=t)
    r = await llm.complete("hi", model="openai/gpt-5.4")
    assert r.text == "hello" and r.cost_usd == 0.0012 and r.provider == "openrouter"


async def test_fallback_to_anthropic_when_openrouter_fails():
    s = load_settings("config.yaml")
    t = FakeTransport(replies=["from claude"], fail_openrouter=True)
    llm = Llm(s, transport=t)
    r = await llm.complete("hi", model="anthropic/claude-sonnet-4.6")
    assert r.provider == "anthropic" and r.text == "from claude"
    assert r.cost_usd == pytest.approx(100 * 3 / 1e6 + 50 * 15 / 1e6)
    assert llm.fallback_used is True


async def test_no_fallback_for_non_anthropic_model():
    s = load_settings("config.yaml")
    t = FakeTransport(fail_openrouter=True)
    llm = Llm(s, transport=t)
    with pytest.raises(LlmError):
        await llm.complete("hi", model="openai/gpt-5.4")


async def test_complete_json_retries_once_then_parses():
    s = load_settings("config.yaml")
    t = FakeTransport(replies=["garbage", '{"a": 3, "b": "y"}'])
    llm = Llm(s, transport=t)
    out, res = await llm.complete_json("p", model="openai/gpt-5.4", out_type=Out)
    assert out.a == 3 and len(t.calls) == 2


async def test_cost_ceiling_raises():
    s = load_settings("config.yaml")
    s.limits.per_call_usd = 0.001
    t = FakeTransport(replies=["x"])
    llm = Llm(s, transport=t)
    with pytest.raises(CostCeilingError):
        await llm.complete("hi", model="openai/gpt-5.4")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.llm'`

- [ ] **Step 3: Write bot/llm.py**

```python
from __future__ import annotations
import json
import os
import re
from typing import Literal, Protocol, TypeVar
from pydantic import BaseModel, ValidationError
from bot.config import Settings

T = TypeVar("T", bound=BaseModel)

ANTHROPIC_PRICES = {  # USD per million tokens (input, output)
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
}
OPENROUTER_EST_PRICES = {  # used only for the pre-call estimate
    "openai/gpt-5.4": (2.5, 15.0),
    "openai/gpt-5.4-mini": (0.75, 4.5),
    "openai/gpt-5.4-mini:online": (0.75, 4.5),
    "anthropic/claude-sonnet-4.6": (3.0, 15.0),
    "x-ai/grok-4.6": (2.0, 6.0),
}


class LlmError(Exception):
    pass


class CostCeilingError(LlmError):
    pass


class LlmResult(BaseModel):
    text: str
    model: str
    cost_usd: float
    prompt_tokens: int
    completion_tokens: int
    provider: Literal["openrouter", "anthropic"]


class Transport(Protocol):
    async def openrouter(self, model: str, messages: list[dict], temperature: float, max_tokens: int) -> dict: ...
    async def anthropic(self, model: str, messages: list[dict], temperature: float, max_tokens: int) -> dict: ...


class HttpTransport:
    """Real transport. OpenRouter via the openai SDK; Anthropic via the anthropic SDK."""

    def __init__(self) -> None:
        from openai import AsyncOpenAI
        self._or = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_API_KEY"), timeout=180)
        self._anthropic = None

    async def openrouter(self, model, messages, temperature, max_tokens):
        resp = await self._or.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens,
            extra_body={"usage": {"include": True}},
        )
        usage = resp.usage
        cost = getattr(usage, "cost", None)
        if cost is None and hasattr(usage, "model_extra"):
            cost = (usage.model_extra or {}).get("cost")
        return {
            "text": resp.choices[0].message.content or "",
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "cost": float(cost) if cost is not None else None,
        }

    async def anthropic(self, model, messages, temperature, max_tokens):
        if self._anthropic is None:
            from anthropic import AsyncAnthropic
            self._anthropic = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), timeout=180)
        system = "\n".join(m["content"] for m in messages if m["role"] == "system") or None
        user_msgs = [m for m in messages if m["role"] != "system"]
        kwargs = {"model": model, "messages": user_msgs, "temperature": temperature, "max_tokens": max_tokens}
        if system:
            kwargs["system"] = system
        resp = await self._anthropic.messages.create(**kwargs)
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        return {"text": text, "prompt_tokens": resp.usage.input_tokens, "completion_tokens": resp.usage.output_tokens, "cost": None}


def extract_json(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [m.group(1)] if m else []
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    raise LlmError("no JSON object found in model output")


class Llm:
    def __init__(self, settings: Settings, transport: Transport | None = None) -> None:
        self.s = settings
        self.t = transport or HttpTransport()
        self.fallback_used = False
        self.total_cost_usd = 0.0

    def _anthropic_direct_name(self, openrouter_model: str) -> str | None:
        if not openrouter_model.startswith("anthropic/"):
            return None
        return openrouter_model.split("/", 1)[1].replace(".", "-")  # claude-sonnet-4.6 -> claude-sonnet-4-6

    def _estimate(self, prompt: str, model: str, max_tokens: int) -> float:
        inp, out = OPENROUTER_EST_PRICES.get(model, (5.0, 25.0))
        return (len(prompt) / 4) * inp / 1e6 + max_tokens * out / 1e6

    async def complete(self, prompt: str, model: str, temperature: float = 0.5, system: str | None = None, max_tokens: int = 4000) -> LlmResult:
        if self._estimate(prompt, model, max_tokens) > 2 * self.s.limits.per_call_usd:
            raise CostCeilingError(f"pre-call estimate exceeds 2x per-call ceiling for {model}")
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        try:
            raw = await self.t.openrouter(model, messages, temperature, max_tokens)
            provider, used_model = "openrouter", model
        except Exception as e:  # noqa: BLE001
            direct = self._anthropic_direct_name(model)
            if direct is None:
                raise LlmError(f"openrouter call failed for {model}: {e}") from e
            self.fallback_used = True
            raw = await self.t.anthropic(direct, messages, temperature, max_tokens)
            provider, used_model = "anthropic", direct
        cost = raw.get("cost")
        if cost is None:
            inp, out = ANTHROPIC_PRICES.get(used_model, (5.0, 25.0))
            cost = raw["prompt_tokens"] * inp / 1e6 + raw["completion_tokens"] * out / 1e6
        res = LlmResult(text=raw["text"], model=used_model, cost_usd=float(cost),
                        prompt_tokens=raw["prompt_tokens"], completion_tokens=raw["completion_tokens"], provider=provider)
        self.total_cost_usd += res.cost_usd
        if res.cost_usd > self.s.limits.per_call_usd:
            raise CostCeilingError(f"call cost {res.cost_usd:.4f} exceeded per-call ceiling")
        return res

    async def complete_json(self, prompt: str, model: str, out_type: type[T], temperature: float = 0.5, retries: int = 1, system: str | None = None, max_tokens: int = 4000) -> tuple[T, LlmResult]:
        last_err: Exception | None = None
        total_cost = 0.0
        for attempt in range(retries + 1):
            res = await self.complete(prompt, model, temperature, system, max_tokens)
            total_cost += res.cost_usd
            try:
                obj = out_type.model_validate(extract_json(res.text))
                res.cost_usd = total_cost
                return obj, res
            except (LlmError, ValidationError) as e:
                last_err = e
                prompt = prompt + "\n\nYour previous reply did not contain a valid JSON object matching the schema. Reply again with ONLY the JSON object."
        raise LlmError(f"could not parse JSON after {retries + 1} attempts: {last_err}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_llm.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add bot/llm.py tests/test_llm.py
git commit -m "feat: LLM wrapper with OpenRouter cost accounting and Anthropic fallback"
```

---

### Task 5: Aggregation math (bot/aggregate.py)

**Files:**
- Create: `bot/aggregate.py`, `tests/test_aggregate.py`

**Interfaces:**
- Consumes: `bot.models.ForecastValue`, `QuestionSummary`.
- Produces:
  - `logit(p) -> float`, `sigmoid(x) -> float`
  - `aggregate_binary(ps: list[float], p_min: float, p_max: float) -> float` (median in logit space, clamped)
  - `aggregate_mc(dicts: list[dict[str, float]], options: list[str], floor: float) -> dict[str, float]` (per-option median, floor, renormalize)
  - `percentiles_to_cdf(percentiles: dict[int, float], q: QuestionSummary) -> list[float]` (via `NumericDistribution.from_question` on a reconstructed question; returns `cdf_size` values)
  - `aggregate_numeric(members: list[dict[int, float]], q: QuestionSummary, target_percentiles: list[int]) -> dict[int, float]` (each member to CDF, pointwise median CDF, read back the target percentiles by interpolation)
  - `aggregate(values: list[ForecastValue], q: QuestionSummary, cfg: ForecastCfg) -> ForecastValue`
  - `bounded_logit_shift(old_p: float, new_p: float, max_shift: float) -> float`

- [ ] **Step 1: Write the failing tests**

`tests/test_aggregate.py`:
```python
import pytest
from bot.aggregate import (logit, sigmoid, aggregate_binary, aggregate_mc, aggregate_numeric,
                           bounded_logit_shift, aggregate, percentiles_to_cdf)
from bot.models import ForecastValue, QuestionSummary
from bot.config import ForecastCfg


def _q(kind="numeric", lo=0.0, hi=100.0, open_lo=False, open_hi=False, cdf_size=201):
    return QuestionSummary(post_id=1, question_id=1, url="u", title="t", kind=kind, close_time=None,
                           options=["A", "B", "C"] if kind == "multiple_choice" else None,
                           lower_bound=lo, upper_bound=hi, open_lower=open_lo, open_upper=open_hi,
                           cdf_size=cdf_size, zero_point=None, unit=None)


def test_logit_roundtrip():
    assert sigmoid(logit(0.3)) == pytest.approx(0.3)


def test_binary_logit_median_and_clamp():
    assert aggregate_binary([0.2, 0.3, 0.9], 0.01, 0.99) == pytest.approx(0.3)
    assert aggregate_binary([0.2, 0.8], 0.01, 0.99) == pytest.approx(0.5)  # logit median of symmetric pair
    assert aggregate_binary([0.999, 0.999], 0.01, 0.99) == 0.99
    assert aggregate_binary([0.0001], 0.01, 0.99) == 0.01


def test_mc_median_floor_renormalize():
    out = aggregate_mc([{"A": 0.9, "B": 0.1, "C": 0.0}, {"A": 0.8, "B": 0.2, "C": 0.0}], ["A", "B", "C"], 0.01)
    assert out["C"] >= 0.01 and sum(out.values()) == pytest.approx(1.0)
    assert out["A"] > out["B"] > out["C"]


def test_percentiles_to_cdf_shape():
    cdf = percentiles_to_cdf({10: 20.0, 50: 50.0, 90: 80.0}, _q())
    assert len(cdf) == 201 and cdf[0] == pytest.approx(0.0) and cdf[-1] == pytest.approx(1.0)
    assert all(b >= a for a, b in zip(cdf, cdf[1:]))


def test_numeric_pointwise_median():
    m = [{10: 10.0, 50: 50.0, 90: 90.0}, {10: 20.0, 50: 60.0, 90: 95.0}, {10: 15.0, 50: 55.0, 90: 92.0}]
    out = aggregate_numeric(m, _q(), [10, 50, 90])
    assert 12 < out[10] < 18 and 52 < out[50] < 58 and 90 < out[90] < 94


def test_bounded_shift():
    assert bounded_logit_shift(0.5, 0.9, 0.5) == pytest.approx(sigmoid(0.5))
    assert bounded_logit_shift(0.5, 0.55, 0.5) == pytest.approx(0.55)


def test_aggregate_dispatch():
    cfg = ForecastCfg()
    v = aggregate([ForecastValue(kind="binary", probability=0.2), ForecastValue(kind="binary", probability=0.4)], _q("binary"), cfg)
    assert v.kind == "binary" and 0.2 < v.probability < 0.4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_aggregate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.aggregate'`

- [ ] **Step 3: Write bot/aggregate.py**

```python
from __future__ import annotations
import math
import statistics
import numpy as np
from forecasting_tools import NumericDistribution, NumericQuestion, DateQuestion
from forecasting_tools.data_models.numeric_report import Percentile
from bot.config import ForecastCfg
from bot.models import ForecastValue, QuestionSummary


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def aggregate_binary(ps: list[float], p_min: float, p_max: float) -> float:
    med = statistics.median(logit(p) for p in ps)
    return min(max(sigmoid(med), p_min), p_max)


def aggregate_mc(dicts: list[dict[str, float]], options: list[str], floor: float) -> dict[str, float]:
    med = {o: statistics.median(d.get(o, 0.0) for d in dicts) for o in options}
    floored = {o: max(v, floor) for o, v in med.items()}
    total = sum(floored.values())
    return {o: v / total for o, v in floored.items()}


def _fake_question(q: QuestionSummary) -> NumericQuestion:
    return NumericQuestion(
        question_text=q.title, lower_bound=q.lower_bound, upper_bound=q.upper_bound,
        open_lower_bound=bool(q.open_lower), open_upper_bound=bool(q.open_upper),
        zero_point=q.zero_point, cdf_size=q.cdf_size or 201,
    )


def percentiles_to_cdf(percentiles: dict[int, float], q: QuestionSummary) -> list[float]:
    pcts = [Percentile(percentile=k / 100, value=float(v)) for k, v in sorted(percentiles.items())]
    dist = NumericDistribution.from_question(pcts, _fake_question(q))
    return [p.percentile for p in dist.cdf]


def _cdf_to_percentiles(cdf: list[float], q: QuestionSummary, targets: list[int]) -> dict[int, float]:
    n = len(cdf)
    xs = np.linspace(q.lower_bound, q.upper_bound, n)
    if q.zero_point is not None:  # log-scaled axis: map linear grid to nominal values
        lo, hi, zp = q.lower_bound, q.upper_bound, q.zero_point
        ratio = (hi - zp) / (lo - zp)
        xs = np.array([zp + (lo - zp) * ratio ** (i / (n - 1)) for i in range(n)])
    out = {}
    for t in targets:
        out[t] = float(np.interp(t / 100, cdf, xs))
    return out


def aggregate_numeric(members: list[dict[int, float]], q: QuestionSummary, target_percentiles: list[int]) -> dict[int, float]:
    cdfs = np.array([percentiles_to_cdf(m, q) for m in members])
    med = np.median(cdfs, axis=0)
    med = np.maximum.accumulate(med)  # keep monotone after pointwise median
    return _cdf_to_percentiles(list(med), q, target_percentiles)


def bounded_logit_shift(old_p: float, new_p: float, max_shift: float) -> float:
    lo, ln = logit(old_p), logit(new_p)
    delta = max(-max_shift, min(max_shift, ln - lo))
    return sigmoid(lo + delta)


def aggregate(values: list[ForecastValue], q: QuestionSummary, cfg: ForecastCfg) -> ForecastValue:
    kind = values[0].kind
    if kind == "binary":
        return ForecastValue(kind="binary", probability=aggregate_binary([v.probability for v in values], cfg.p_min, cfg.p_max))
    if kind == "multiple_choice":
        return ForecastValue(kind="multiple_choice", options=aggregate_mc([v.options for v in values], q.options, cfg.mc_floor))
    return ForecastValue(kind=kind, percentiles=aggregate_numeric([v.percentiles for v in values], q, cfg.numeric_percentiles))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_aggregate.py -v`
Expected: 7 PASSED. If `NumericDistribution.from_question` rejects the fake question because a required field is missing, add that field with a neutral default to `_fake_question` and re-run; the test asserts only shape and monotonicity.

- [ ] **Step 5: Commit**

```bash
git add bot/aggregate.py tests/test_aggregate.py
git commit -m "feat: logit-median, MC, and pointwise-CDF aggregation"
```

---

### Task 6: Guards (bot/guards.py)

**Files:**
- Create: `bot/guards.py`, `tests/test_guards.py`

**Interfaces:**
- Consumes: `bot.models.*`, `bot.config.Settings`.
- Produces:
  - `consistency_ok(m: MemberForecast, tol: float = 0.05) -> bool` (binary: |json − stated| ≤ tol; MC: stated number, if any, must match the top option's probability within tol; numeric: stated number, if any, must lie between p10 and p90).
  - `validate_value(v: ForecastValue, q: QuestionSummary) -> list[str]` returns problems: binary outside (0,1); MC keys ≠ options or sum not ≈ 1; numeric percentiles not strictly increasing, or violating closed bounds.
  - `drop_invalid_members(members: list[MemberForecast], q: QuestionSummary) -> list[MemberForecast]` sets `dropped_reason` on bad ones and returns survivors.
  - `enough_members(survivors: list[MemberForecast], min_members: int) -> bool`
  - `class Budget`: `__init__(self, wall_clock_s: int, per_question_usd: float)`; `elapsed_fraction() -> float`; `spent_fraction(cost) -> float`; `should_skip_da(cost, frac) -> bool`; `exhausted(cost) -> bool`.
  - `season_spent(runs_dir: str) -> float` sums `cost_usd` over all `runs/**/*.json`.

- [ ] **Step 1: Write the failing tests**

`tests/test_guards.py`:
```python
import json, time
from bot.guards import consistency_ok, validate_value, drop_invalid_members, enough_members, Budget, season_spent
from bot.models import ForecastValue, MemberForecast, QuestionSummary


def _q(kind="binary", **kw):
    base = dict(post_id=1, question_id=1, url="u", title="t", kind=kind, close_time=None, options=None,
                lower_bound=None, upper_bound=None, open_lower=None, open_upper=None, cdf_size=None, zero_point=None, unit=None)
    base.update(kw)
    return QuestionSummary(**base)


def _m(v, stated=None):
    return MemberForecast(name="a", model="m", forecast=v, reasoning="r", stated_number=stated)


def test_consistency_binary():
    assert consistency_ok(_m(ForecastValue(kind="binary", probability=0.42), stated=0.4))
    assert not consistency_ok(_m(ForecastValue(kind="binary", probability=0.2), stated=0.8))
    assert consistency_ok(_m(ForecastValue(kind="binary", probability=0.2), stated=None))


def test_validate_binary_and_mc():
    assert validate_value(ForecastValue(kind="binary", probability=1.2), _q()) != []
    q = _q("multiple_choice", options=["A", "B"])
    assert validate_value(ForecastValue(kind="multiple_choice", options={"A": 0.5, "B": 0.5}), q) == []
    assert validate_value(ForecastValue(kind="multiple_choice", options={"A": 0.5, "C": 0.5}), q) != []


def test_validate_numeric_bounds():
    q = _q("numeric", lower_bound=0.0, upper_bound=10.0, open_lower=False, open_upper=False)
    assert validate_value(ForecastValue(kind="numeric", percentiles={10: 1.0, 50: 5.0, 90: 9.0}), q) == []
    assert validate_value(ForecastValue(kind="numeric", percentiles={10: 5.0, 50: 4.0, 90: 9.0}), q) != []
    assert validate_value(ForecastValue(kind="numeric", percentiles={10: -1.0, 50: 4.0, 90: 9.0}), q) != []


def test_drop_and_enough():
    good = _m(ForecastValue(kind="binary", probability=0.3), 0.3)
    bad = _m(ForecastValue(kind="binary", probability=0.3), 0.9)
    survivors = drop_invalid_members([good, bad], _q())
    assert survivors == [good] and bad.dropped_reason is not None
    assert not enough_members(survivors, 2) and enough_members(survivors, 1)


def test_budget():
    b = Budget(wall_clock_s=100, per_question_usd=1.0)
    assert b.elapsed_fraction() < 0.05
    assert b.should_skip_da(cost=0.8, frac=0.7) and not b.should_skip_da(cost=0.2, frac=0.7)
    assert b.exhausted(cost=1.01) and not b.exhausted(cost=0.5)


def test_season_spent(tmp_path):
    d = tmp_path / "2026-09-12"; d.mkdir()
    (d / "a.json").write_text(json.dumps({"cost_usd": 0.4}))
    (d / "b.json").write_text(json.dumps({"cost_usd": 0.6}))
    assert season_spent(str(tmp_path)) == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_guards.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.guards'`

- [ ] **Step 3: Write bot/guards.py**

```python
from __future__ import annotations
import json
import time
from pathlib import Path
from bot.models import ForecastValue, MemberForecast, QuestionSummary


def consistency_ok(m: MemberForecast, tol: float = 0.05) -> bool:
    v, s = m.forecast, m.stated_number
    if s is None:
        return True
    if v.kind == "binary":
        return abs(v.probability - s) <= tol
    if v.kind == "multiple_choice":
        top = max(v.options.values())
        return abs(top - s) <= tol
    ps = v.percentiles
    lo, hi = ps.get(10, min(ps.values())), ps.get(90, max(ps.values()))
    return lo <= s <= hi


def validate_value(v: ForecastValue, q: QuestionSummary) -> list[str]:
    problems: list[str] = []
    if v.kind == "binary":
        if v.probability is None or not (0 < v.probability < 1):
            problems.append("binary probability out of (0,1)")
    elif v.kind == "multiple_choice":
        if v.options is None or set(v.options) != set(q.options or []):
            problems.append("option keys do not match question options")
        elif abs(sum(v.options.values()) - 1) > 0.02:
            problems.append("option probabilities do not sum to 1")
    else:
        if not v.percentiles:
            problems.append("no percentiles")
        else:
            vals = [v.percentiles[k] for k in sorted(v.percentiles)]
            if any(b <= a for a, b in zip(vals, vals[1:])):
                problems.append("percentiles not strictly increasing")
            if q.lower_bound is not None and q.open_lower is False and vals[0] < q.lower_bound:
                problems.append("value below closed lower bound")
            if q.upper_bound is not None and q.open_upper is False and vals[-1] > q.upper_bound:
                problems.append("value above closed upper bound")
    return problems


def drop_invalid_members(members: list[MemberForecast], q: QuestionSummary) -> list[MemberForecast]:
    survivors = []
    for m in members:
        probs = validate_value(m.forecast, q)
        if probs:
            m.dropped_reason = "; ".join(probs)
        elif not consistency_ok(m):
            m.dropped_reason = "stated number disagrees with JSON forecast"
        else:
            survivors.append(m)
    return survivors


def enough_members(survivors: list[MemberForecast], min_members: int) -> bool:
    return len(survivors) >= min_members


class Budget:
    def __init__(self, wall_clock_s: int, per_question_usd: float) -> None:
        self.start = time.monotonic()
        self.wall = wall_clock_s
        self.cap = per_question_usd

    def elapsed_fraction(self) -> float:
        return (time.monotonic() - self.start) / self.wall

    def spent_fraction(self, cost: float) -> float:
        return cost / self.cap

    def should_skip_da(self, cost: float, frac: float) -> bool:
        return self.elapsed_fraction() >= frac or self.spent_fraction(cost) >= frac

    def exhausted(self, cost: float) -> bool:
        return self.elapsed_fraction() >= 1.0 or cost > self.cap


def season_spent(runs_dir: str) -> float:
    total = 0.0
    for p in Path(runs_dir).glob("**/*.json"):
        try:
            total += float(json.loads(p.read_text(encoding="utf-8")).get("cost_usd", 0.0))
        except (json.JSONDecodeError, OSError):
            continue
    return total
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_guards.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add bot/guards.py tests/test_guards.py
git commit -m "feat: publish guards, validation, and budgets"
```

---
### Task 7: Tradecraft stages (bot/stages/*.py)

**Files:**
- Create: `bot/stages/__init__.py`, `bot/stages/common.py`, `bot/stages/forensics.py`, `bot/stages/base_rate.py`, `bot/stages/evidence.py`, `bot/stages/forecast.py`, `bot/stages/devils_advocate.py`, `tests/test_stages.py`, `tests/fixtures/forensics_binary.json`, `tests/fixtures/forecast_binary.txt`

**Interfaces:**
- Consumes: `bot.llm.Llm` (`complete`, `complete_json`), `bot.models.*`, `bot.config.Settings`.
- Produces (every stage has the same shape so the pipeline can treat them uniformly):
  - `forensics.build_prompt(q: QuestionSummary, description: str, criteria: str, fine_print: str, today: str) -> str`; `forensics.run(llm, settings, q, description, criteria, fine_print, today) -> tuple[Forensics, LlmResult]`
  - `base_rate.build_prompt(q, description, criteria, forensics: Forensics, today) -> str`; `base_rate.run(...) -> tuple[BlindEstimate, LlmResult]`
  - `evidence.build_prompt(q, forensics, bundle: ResearchBundle, today) -> str`; `evidence.run(llm, settings, q, forensics, bundle, today) -> tuple[EvidenceTable, LlmResult]`
  - `forecast.build_prompt(q, description, criteria, fine_print, forensics, blind: BlindEstimate | None, evidence: EvidenceTable | None, today, percentiles: list[int]) -> str`; `forecast.parse(text: str, q) -> tuple[ForecastValue, float | None]` (JSON forecast + number stated in prose); `forecast.run_member(llm, settings, member: Member, q, ..., today) -> MemberForecast`
  - `devils_advocate.critique_prompt(q, forensics, evidence, aggregate: ForecastValue) -> str`; `devils_advocate.revise_prompt(q, aggregate, critique, percentiles) -> str`; `devils_advocate.run(llm, settings, q, forensics, evidence, aggregate, today) -> tuple[ForecastValue, str, float]` returning (revised value **before** bounding, critique text, cost).
  - `common.question_block(q, description, criteria, fine_print, today) -> str` shared header; `common.CONVENTION` string; `common.forecast_json_instructions(q, percentiles) -> str`; `common.parse_forecast_json(d: dict, q) -> ForecastValue`.

Design notes: all stage prompts end with a required fenced JSON block. `Llm.complete_json` parses it. The forecast stage additionally asks for a one-line prose statement `FINAL: <number>` so the consistency guard has something to compare.

- [ ] **Step 1: Write common.py**

```python
from __future__ import annotations
from bot.models import ForecastValue, QuestionSummary

CONVENTION = (
    "Metaculus convention: assume the event described has NOT yet happened unless the evidence you are "
    "given explicitly shows that it has. 'Before <date>' questions are forward-looking from today. "
    "'As of <date>' questions are snapshots at that date. Read the resolution criteria literally."
)


def question_block(q: QuestionSummary, description: str, criteria: str, fine_print: str, today: str) -> str:
    bounds = ""
    if q.kind in ("numeric", "discrete", "date"):
        bounds = (f"\nRange: lower bound {q.lower_bound} ({'open' if q.open_lower else 'closed'}), "
                  f"upper bound {q.upper_bound} ({'open' if q.open_upper else 'closed'}). Units: {q.unit or 'not stated'}.")
    opts = f"\nOptions: {q.options}" if q.options else ""
    return (f"Today is {today}.\nQuestion type: {q.kind}\nTitle: {q.title}{opts}{bounds}\n"
            f"Close time: {q.close_time}\n\nBackground:\n{description}\n\nResolution criteria:\n{criteria}\n\nFine print:\n{fine_print}\n")


def forecast_json_instructions(q: QuestionSummary, percentiles: list[int]) -> str:
    if q.kind == "binary":
        return 'Finish with a fenced JSON block exactly like: ```json\n{"probability": 0.23}\n```'
    if q.kind == "multiple_choice":
        return ('Finish with a fenced JSON block mapping EVERY option name verbatim to a probability that sums to 1, exactly like: '
                '```json\n{"options": {"Option A": 0.6, "Option B": 0.4}}\n```')
    keys = ", ".join(f'"{p}": <value>' for p in percentiles)
    return (f"Finish with a fenced JSON block giving strictly increasing values at these percentiles, in the question's units, "
            f"never scientific notation: ```json\n{{\"percentiles\": {{{keys}}}}}\n```")


def parse_forecast_json(d: dict, q: QuestionSummary) -> ForecastValue:
    if q.kind == "binary":
        return ForecastValue(kind="binary", probability=float(d["probability"]))
    if q.kind == "multiple_choice":
        return ForecastValue(kind="multiple_choice", options={k: float(v) for k, v in d["options"].items()})
    return ForecastValue(kind=q.kind, percentiles={int(k): float(v) for k, v in d["percentiles"].items()})
```

- [ ] **Step 2: Write the failing tests**

`tests/fixtures/forensics_binary.json`:
```json
{"resolution_statement": "Resolves Yes if X is officially announced by 2026-10-01 per the named source.", "status_quo_outcome": "No", "key_dates": ["2026-10-01"], "traps": ["'before' means strictly earlier than the date"], "possibly_already_resolved": false, "already_resolved_reason": "", "search_queries": ["X announcement", "X official statement September 2026"], "things_that_do_not_count": ["rumors", "unofficial leaks"]}
```

`tests/fixtures/forecast_binary.txt`:
```
H0 (status quo): No announcement by the deadline.
H1: Announcement happens.
Evidence table check: E1 supports H1 weakly (C3). E2 supports H0 (B2).
What must change: an official statement within 19 days.
FINAL: 0.18
```json
{"probability": 0.18}
```
```

`tests/test_stages.py`:
```python
import json
from pathlib import Path
from bot.config import load_settings
from bot.models import QuestionSummary, Forensics, BlindEstimate, EvidenceTable, Evidence, ForecastValue, ResearchBundle, RawSource
from bot.stages import forensics, base_rate, evidence, forecast, devils_advocate
from bot.stages.common import parse_forecast_json

FIX = Path("tests/fixtures")


def _q(kind="binary"):
    return QuestionSummary(post_id=1, question_id=1, url="u", title="Will X happen before 2026-10-01?", kind=kind, close_time="2026-09-30T00:00:00+00:00",
                           options=["A", "B"] if kind == "multiple_choice" else None, lower_bound=0.0 if kind == "numeric" else None,
                           upper_bound=100.0 if kind == "numeric" else None, open_lower=False, open_upper=False, cdf_size=201, zero_point=None, unit="count")


class FakeLlm:
    def __init__(self, texts):
        self.texts = list(texts)
        self.prompts = []

    async def complete(self, prompt, model, temperature=0.5, system=None, max_tokens=4000):
        from bot.llm import LlmResult
        self.prompts.append(prompt)
        return LlmResult(text=self.texts.pop(0), model=model, cost_usd=0.01, prompt_tokens=1, completion_tokens=1, provider="openrouter")

    async def complete_json(self, prompt, model, out_type, temperature=0.5, retries=1, system=None, max_tokens=4000):
        from bot.llm import extract_json
        res = await self.complete(prompt, model, temperature, system, max_tokens)
        return out_type.model_validate(extract_json(res.text)), res


def test_forensics_prompt_and_parse():
    s = load_settings("config.yaml")
    text = "analysis...\n```json\n" + (FIX / "forensics_binary.json").read_text() + "\n```"
    llm = FakeLlm([text])
    import asyncio
    f, res = asyncio.run(forensics.run(llm, s, _q(), "desc", "crit", "fine", "2026-09-12"))
    assert isinstance(f, Forensics) and f.status_quo_outcome == "No" and len(f.search_queries) == 2
    assert "NOT yet happened" in llm.prompts[0] and "Resolution criteria" in llm.prompts[0]


def test_forecast_parse_binary_with_stated_number():
    v, stated = forecast.parse((FIX / "forecast_binary.txt").read_text(), _q())
    assert v.probability == 0.18 and stated == 0.18


def test_forecast_parse_numeric():
    text = 'reasoning\nFINAL: 50\n```json\n{"percentiles": {"10": 20, "50": 50, "90": 80}}\n```'
    v, stated = forecast.parse(text, _q("numeric"))
    assert v.percentiles == {10: 20.0, 50: 50.0, 90: 80.0} and stated == 50.0


def test_forecast_prompt_includes_blind_and_evidence():
    s = load_settings("config.yaml")
    f = Forensics.model_validate(json.loads((FIX / "forensics_binary.json").read_text()))
    b = BlindEstimate(reference_class="rc", base_rate_reasoning="br", forecast=ForecastValue(kind="binary", probability=0.2))
    e = EvidenceTable(items=[Evidence(claim="c", source="s", reliability="B", credibility=2, supports="Yes")])
    p = forecast.build_prompt(_q(), "d", "c", "f", f, b, e, "2026-09-12", s.forecast.numeric_percentiles)
    assert "reference class" in p.lower() and "B2" in p and "status quo" in p.lower() and "FINAL:" in p


def test_evidence_prompt_lists_sources():
    f = Forensics.model_validate(json.loads((FIX / "forensics_binary.json").read_text()))
    bundle = ResearchBundle(sources=[RawSource(provider="asknews", url="http://a", title="T", published="2026-09-10", text="body")])
    p = evidence.build_prompt(_q(), f, bundle, "2026-09-12")
    assert "http://a" in p and "reliability" in p.lower()


def test_da_prompts():
    f = Forensics.model_validate(json.loads((FIX / "forensics_binary.json").read_text()))
    e = EvidenceTable()
    agg = ForecastValue(kind="binary", probability=0.18)
    assert "0.18" in devils_advocate.critique_prompt(_q(), f, e, agg)
    assert "critique" in devils_advocate.revise_prompt(_q(), agg, "the critique text", [10, 50, 90]).lower()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stages.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.stages'`

- [ ] **Step 4: Write bot/stages/forensics.py**

```python
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
```

- [ ] **Step 5: Write bot/stages/base_rate.py**

```python
from __future__ import annotations
from bot.llm import Llm, LlmResult
from bot.config import Settings
from bot.models import BlindEstimate, Forensics, QuestionSummary
from bot.stages.common import CONVENTION, question_block, forecast_json_instructions, parse_forecast_json
from pydantic import BaseModel

SYSTEM = "You are a calibrated forecaster producing an outside-view estimate. You have NO news access; use only general knowledge and base rates."


class _Out(BaseModel):
    reference_class: str
    base_rate_reasoning: str
    forecast: dict


def build_prompt(q: QuestionSummary, description: str, criteria: str, forensics: Forensics, today: str) -> str:
    return f"""{question_block(q, description, criteria, "", today)}
{CONVENTION}
Resolution forensics summary: {forensics.resolution_statement}
Status quo outcome: {forensics.status_quo_outcome}

Produce a BLIND outside-view estimate without any current news:
1. Choose a reference class: what kind of event is this, and how often do such things happen in comparable windows? Be concrete about the class and its size.
2. Give the base rate and adjust only for structural features visible in the question itself (time remaining, how many things must go right, whether the status quo is sticky).
3. State the estimate.

{forecast_json_instructions(q, [5, 10, 20, 40, 60, 80, 90, 95])}
Wrap it so the JSON object has the keys "reference_class", "base_rate_reasoning", and "forecast" (the forecast object described above)."""


async def run(llm: Llm, settings: Settings, q: QuestionSummary, description: str, criteria: str, forensics: Forensics, today: str) -> tuple[BlindEstimate, LlmResult]:
    prompt = build_prompt(q, description, criteria, forensics, today)
    out, res = await llm.complete_json(prompt, settings.models.forecast_tier, _Out, temperature=0.3, system=SYSTEM)
    return BlindEstimate(reference_class=out.reference_class, base_rate_reasoning=out.base_rate_reasoning,
                         forecast=parse_forecast_json(out.forecast, q)), res
```

- [ ] **Step 6: Write bot/stages/evidence.py**

```python
from __future__ import annotations
from bot.llm import Llm, LlmResult
from bot.config import Settings
from bot.models import EvidenceTable, Forensics, QuestionSummary, ResearchBundle

SYSTEM = "You are an intelligence analyst grading sources. You extract claims and grade them; you do not forecast."

GRADES = """Reliability of the SOURCE (track record): A completely reliable (official primary source), B usually reliable (major wire service, regulator filing), C fairly reliable (established outlet), D not usually reliable (partisan, aggregator), E unreliable (anonymous social post), F cannot be judged.
Credibility of the CLAIM: 1 confirmed by independent sources, 2 probably true, 3 possibly true, 4 doubtful, 5 improbable, 6 cannot be judged."""


def build_prompt(q: QuestionSummary, forensics: Forensics, bundle: ResearchBundle, today: str) -> str:
    srcs = "\n\n".join(
        f"[S{i}] provider={s.provider} url={s.url} title={s.title} published={s.published}\n{s.text}"
        for i, s in enumerate(bundle.sources, 1)
    ) or "(no sources retrieved)"
    outcomes = q.options if q.options else (["Yes", "No"] if q.kind == "binary" else ["higher", "lower"])
    return f"""Today is {today}. Question: {q.title}
Resolution forensics: {forensics.resolution_statement}
Traps to watch: {forensics.traps}
Possible outcomes to tag evidence against: {outcomes} (or "context" if it bears on neither).

{GRADES}

Sources:
{srcs}

Extract every claim that bears on the outcome. One row per claim. Prefer the newest and most authoritative. Mark the date the claim refers to, not the retrieval date. If any source shows the event has ALREADY happened or the question is already decided, describe that in "already_resolved_signal", else leave it empty.

Finish with a fenced JSON block:
```json
{{"items": [{{"claim": "...", "source": "S1 url or name", "date": "YYYY-MM-DD or null", "reliability": "A-F", "credibility": 1, "supports": "one of the outcomes or context", "note": ""}}], "already_resolved_signal": ""}}
```"""


async def run(llm: Llm, settings: Settings, q: QuestionSummary, forensics: Forensics, bundle: ResearchBundle, today: str) -> tuple[EvidenceTable, LlmResult]:
    prompt = build_prompt(q, forensics, bundle, today)
    return await llm.complete_json(prompt, settings.models.cheap_tier, EvidenceTable, temperature=0.1, system=SYSTEM, max_tokens=6000)
```

- [ ] **Step 7: Write bot/stages/forecast.py**

```python
from __future__ import annotations
import re
from bot.config import Member, Settings
from bot.llm import Llm, extract_json
from bot.models import BlindEstimate, EvidenceTable, Forensics, ForecastValue, MemberForecast, QuestionSummary
from bot.stages.common import CONVENTION, question_block, forecast_json_instructions, parse_forecast_json

SYSTEM = "You are a superforecaster applying analysis of competing hypotheses. You are calibrated: you avoid extreme probabilities unless the evidence is decisive, and you give extra weight to the status quo."


def _fmt_value(v: ForecastValue) -> str:
    if v.kind == "binary":
        return f"P(Yes) = {v.probability:.2f}"
    if v.kind == "multiple_choice":
        return ", ".join(f"{k}: {p:.2f}" for k, p in v.options.items())
    return ", ".join(f"p{k}={val}" for k, val in sorted(v.percentiles.items()))


def build_prompt(q, description, criteria, fine_print, forensics: Forensics, blind: BlindEstimate | None,
                 evidence: EvidenceTable | None, today: str, percentiles: list[int]) -> str:
    blind_txt = "(blind base rate stage disabled)"
    if blind:
        blind_txt = f"Reference class: {blind.reference_class}\nBase-rate reasoning: {blind.base_rate_reasoning}\nBlind estimate: {_fmt_value(blind.forecast)}"
    ev_txt = "(evidence table stage disabled)"
    if evidence:
        rows = [f"E{i} [{e.reliability}{e.credibility}] ({e.date or 'n/d'}) supports {e.supports}: {e.claim} — {e.source}" for i, e in enumerate(evidence.items, 1)]
        ev_txt = "\n".join(rows) or "(no evidence extracted)"
        if evidence.already_resolved_signal:
            ev_txt += f"\nALREADY-RESOLVED SIGNAL: {evidence.already_resolved_signal}"
    return f"""{question_block(q, description, criteria, fine_print, today)}
{CONVENTION}

RESOLUTION FORENSICS
{forensics.resolution_statement}
Status quo outcome: {forensics.status_quo_outcome}
Traps: {forensics.traps}
Does not count: {forensics.things_that_do_not_count}

OUTSIDE VIEW (blind)
{blind_txt}

EVIDENCE TABLE (source reliability A-F, claim credibility 1-6)
{ev_txt}

Apply analysis of competing hypotheses:
1. List the hypotheses. H0 is the status quo outcome. Others are the alternatives (each option, or higher/lower ranges).
2. For each evidence item, say which hypotheses it is consistent with and which it contradicts. Weight by grade: A1-B2 evidence dominates; D-F or 4-6 barely moves you.
3. State what must change between today and close for a non-status-quo outcome, and how likely that is in the time left.
4. Start from the blind base rate and update on the evidence. Say how far you moved and why.
5. Give the forecast. Do not exceed 0.95 or go below 0.05 unless A1/A2 evidence makes the outcome near-certain.

Write one line "FINAL: <number>" giving the headline number (the Yes probability, the top option's probability, or your median), then
{forecast_json_instructions(q, percentiles)}"""


def parse(text: str, q: QuestionSummary) -> tuple[ForecastValue, float | None]:
    value = parse_forecast_json(extract_json(text), q)
    m = re.search(r"FINAL:\s*([-+]?\d[\d,]*\.?\d*)\s*(%?)", text)
    stated = None
    if m:
        stated = float(m.group(1).replace(",", ""))
        if m.group(2) == "%" or (q.kind in ("binary", "multiple_choice") and stated > 1):
            stated = stated / 100
    return value, stated


async def run_member(llm: Llm, settings: Settings, member: Member, q, description, criteria, fine_print, forensics, blind, evidence, today) -> MemberForecast:
    prompt = build_prompt(q, description, criteria, fine_print, forensics, blind, evidence, today, settings.forecast.numeric_percentiles)
    res = await llm.complete(prompt, member.model, temperature=member.temperature, system=SYSTEM, max_tokens=5000)
    try:
        value, stated = parse(res.text, q)
    except Exception as e:  # noqa: BLE001
        return MemberForecast(name=member.name, model=res.model, forecast=ForecastValue(kind=q.kind), reasoning=res.text,
                              stated_number=None, cost_usd=res.cost_usd, dropped_reason=f"parse failure: {e}")
    return MemberForecast(name=member.name, model=res.model, forecast=value, reasoning=res.text, stated_number=stated, cost_usd=res.cost_usd)
```

- [ ] **Step 8: Write bot/stages/devils_advocate.py**

```python
from __future__ import annotations
from bot.config import Settings
from bot.llm import Llm, extract_json
from bot.models import EvidenceTable, Forensics, ForecastValue, QuestionSummary
from bot.stages.common import forecast_json_instructions, parse_forecast_json
from bot.stages.forecast import _fmt_value

CRITIC_SYSTEM = "You are the devil's advocate on an analytic red team. Your job is to find the strongest case that the team's forecast is wrong."
JUDGE_SYSTEM = "You are the senior analyst adjudicating between a forecast and a red-team critique. Move only as far as the critique's evidence justifies."


def critique_prompt(q: QuestionSummary, forensics: Forensics, evidence: EvidenceTable, aggregate: ForecastValue) -> str:
    rows = "\n".join(f"E{i} [{e.reliability}{e.credibility}] supports {e.supports}: {e.claim}" for i, e in enumerate(evidence.items, 1)) or "(none)"
    return f"""Question: {q.title}
Resolution: {forensics.resolution_statement}
Team forecast: {_fmt_value(aggregate)}
Evidence used:
{rows}

Argue the strongest case that this forecast is wrong in DIRECTION or MAGNITUDE. Consider: a misread resolution criterion, an already-resolved signal, over-weighting low-grade evidence, ignoring the base rate, ignoring time remaining, or an overlooked mechanism. Be specific and cite the evidence ids. End with one sentence: which direction the forecast should move, and roughly how much, or 'no change' if the critique is weak."""


def revise_prompt(q: QuestionSummary, aggregate: ForecastValue, critique: str, percentiles: list[int]) -> str:
    return f"""Question: {q.title}
Current forecast: {_fmt_value(aggregate)}

Red-team critique:
{critique}

Decide whether the critique justifies a change. Small moves are normal; large moves need decisive evidence named in the critique. Explain in three sentences, then
{forecast_json_instructions(q, percentiles)}"""


async def run(llm: Llm, settings: Settings, q: QuestionSummary, forensics: Forensics, evidence: EvidenceTable, aggregate: ForecastValue, today: str) -> tuple[ForecastValue, str, float]:
    c = await llm.complete(critique_prompt(q, forensics, evidence, aggregate), settings.models.forecast_tier, temperature=0.6, system=CRITIC_SYSTEM, max_tokens=2500)
    r = await llm.complete(revise_prompt(q, aggregate, c.text, settings.forecast.numeric_percentiles), settings.models.forecast_tier, temperature=0.2, system=JUDGE_SYSTEM, max_tokens=2500)
    revised = parse_forecast_json(extract_json(r.text), q)
    return revised, c.text, c.cost_usd + r.cost_usd
```

- [ ] **Step 9: Write bot/stages/__init__.py** (empty file) and run tests

Run: `.venv/Scripts/python.exe -m pytest tests/test_stages.py -v`
Expected: 6 PASSED

- [ ] **Step 10: Commit**

```bash
git add bot/stages tests/test_stages.py tests/fixtures
git commit -m "feat: five tradecraft stages with prompts and parsers"
```

---
### Task 8: Research providers (bot/stages/research.py)

**Files:**
- Create: `bot/stages/research.py`, `tests/test_research.py`, `tests/fixtures/resolution_page.html`

**Interfaces:**
- Consumes: `bot.llm.Llm`, `bot.config.Settings`, `bot.models.RawSource`, `ResearchBundle`, `Forensics`.
- Produces:
  - `extract_urls(text: str) -> list[str]`
  - `html_to_text(html: str, max_chars: int) -> str` (trafilatura, fallback to tag-stripping)
  - `async fetch_resolution_sources(urls: list[str], timeout_s: int, max_chars: int, client: httpx.AsyncClient | None = None) -> list[RawSource]`
  - `async asknews_search(queries: list[str], max_queries: int) -> list[RawSource]` (uses `AskNewsSearcher().get_formatted_news_async(q)`; one RawSource per query with the formatted text)
  - `async web_search(llm, settings, queries: list[str]) -> tuple[list[RawSource], float]` (one `complete` call per query on `settings.models.web_search`, prompt asks for dated findings with URLs; returns cost)
  - `async run(llm, settings, forensics: Forensics, criteria_text: str, background_text: str) -> tuple[ResearchBundle, float]` runs enabled providers concurrently with `asyncio.wait_for` per provider; a failing provider adds `diagnostics[provider] = str(err)` and contributes no sources.

- [ ] **Step 1: Write the failing tests**

`tests/fixtures/resolution_page.html`:
```html
<html><head><title>Official Statement</title></head><body><nav>menu</nav><article><h1>Statement</h1><p>The agency confirms the program will begin on 2026-10-15.</p></article></body></html>
```

`tests/test_research.py`:
```python
import asyncio
import httpx
from bot.config import load_settings
from bot.models import Forensics
from bot.stages import research


def test_extract_urls():
    t = "see https://example.com/a and http://b.org/x?y=1. Also https://c.net."
    assert research.extract_urls(t) == ["https://example.com/a", "http://b.org/x?y=1", "https://c.net"]


def test_html_to_text():
    html = open("tests/fixtures/resolution_page.html", encoding="utf-8").read()
    txt = research.html_to_text(html, 500)
    assert "2026-10-15" in txt and "menu" not in txt


async def test_fetch_resolution_sources_with_mock_transport():
    html = open("tests/fixtures/resolution_page.html", encoding="utf-8").read()

    def handler(request):
        if "bad" in str(request.url):
            return httpx.Response(500)
        return httpx.Response(200, text=html)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    out = await research.fetch_resolution_sources(["https://good.example/x", "https://bad.example/y"], 5, 500, client=client)
    assert len(out) == 1 and out[0].provider == "resolution_source" and "2026-10-15" in out[0].text


async def test_run_isolates_provider_failures(monkeypatch):
    s = load_settings("config.yaml")
    s.research.asknews_enabled = True
    s.research.web_search_enabled = False
    s.research.resolution_fetch_enabled = False

    async def boom(queries, max_queries):
        raise RuntimeError("asknews down")

    monkeypatch.setattr(research, "asknews_search", boom)
    f = Forensics(resolution_statement="r", status_quo_outcome="No", search_queries=["q1"])
    bundle, cost = await research.run(llm=None, settings=s, forensics=f, criteria_text="", background_text="")
    assert bundle.sources == [] and "asknews" in bundle.diagnostics and cost == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_research.py -v`
Expected: FAIL with `ImportError: cannot import name 'research'`

- [ ] **Step 3: Write bot/stages/research.py**

```python
from __future__ import annotations
import asyncio
import re
import httpx
from bot.config import Settings
from bot.models import Forensics, RawSource, ResearchBundle

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def extract_urls(text: str) -> list[str]:
    seen, out = set(), []
    for m in URL_RE.findall(text or ""):
        u = m.rstrip(".,;:")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def html_to_text(html: str, max_chars: int) -> str:
    try:
        import trafilatura
        txt = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
    except Exception:  # noqa: BLE001
        txt = ""
    if not txt:
        txt = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        txt = re.sub(r"<[^>]+>", " ", txt)
        txt = re.sub(r"\s+", " ", txt).strip()
    return txt[:max_chars]


async def fetch_resolution_sources(urls: list[str], timeout_s: int, max_chars: int, client: httpx.AsyncClient | None = None) -> list[RawSource]:
    own = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, timeout=timeout_s, headers={"User-Agent": "Mozilla/5.0 (forecasting-bot)"})
    out: list[RawSource] = []
    try:
        for u in urls[:4]:
            try:
                r = await client.get(u)
                if r.status_code != 200:
                    continue
                text = html_to_text(r.text, max_chars)
                if text:
                    out.append(RawSource(provider="resolution_source", url=u, title=None, published=None, text=text))
            except Exception:  # noqa: BLE001
                continue
    finally:
        if own:
            await client.aclose()
    return out


async def asknews_search(queries: list[str], max_queries: int) -> list[RawSource]:
    from forecasting_tools import AskNewsSearcher
    searcher = AskNewsSearcher()
    out = []
    for q in queries[:max_queries]:
        text = await searcher.get_formatted_news_async(q)
        if text:
            out.append(RawSource(provider="asknews", url=None, title=q, published=None, text=text))
    return out


async def web_search(llm, settings: Settings, queries: list[str]) -> tuple[list[RawSource], float]:
    out, cost = [], 0.0
    for q in queries[: settings.research.max_queries]:
        prompt = (f"Search the web for: {q}\nReport the most relevant, most recent findings as bullet points. "
                  f"Each bullet: date (YYYY-MM-DD), the fact, and the source URL. Prefer official and primary sources. No speculation.")
        res = await llm.complete(prompt, settings.models.web_search, temperature=0.1, max_tokens=1500)
        cost += res.cost_usd
        if res.text.strip():
            out.append(RawSource(provider="web_search", url=None, title=q, published=None, text=res.text[: settings.research.source_text_max_chars]))
    return out, cost


async def run(llm, settings: Settings, forensics: Forensics, criteria_text: str, background_text: str) -> tuple[ResearchBundle, float]:
    cfg = settings.research
    queries = forensics.search_queries or []
    tasks: dict[str, asyncio.Task] = {}
    if cfg.asknews_enabled:
        tasks["asknews"] = asyncio.create_task(asyncio.wait_for(asknews_search(queries, cfg.max_queries), cfg.provider_timeout_s))
    if cfg.web_search_enabled and llm is not None:
        tasks["web_search"] = asyncio.create_task(asyncio.wait_for(web_search(llm, settings, queries), cfg.provider_timeout_s))
    if cfg.resolution_fetch_enabled:
        urls = extract_urls(criteria_text) + [u for u in extract_urls(background_text) if u not in extract_urls(criteria_text)]
        tasks["resolution_source"] = asyncio.create_task(asyncio.wait_for(fetch_resolution_sources(urls, cfg.provider_timeout_s, cfg.source_text_max_chars), cfg.provider_timeout_s))
    bundle, cost = ResearchBundle(), 0.0
    for name, t in tasks.items():
        try:
            result = await t
        except Exception as e:  # noqa: BLE001
            bundle.diagnostics[name] = f"{type(e).__name__}: {e}"
            continue
        if name == "web_search":
            srcs, c = result
            cost += c
        else:
            srcs = result
        bundle.sources.extend(srcs)
    return bundle, cost
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_research.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add bot/stages/research.py tests/test_research.py tests/fixtures/resolution_page.html
git commit -m "feat: research providers with isolation and timeouts"
```

---

### Task 9: Comment builder and run records (bot/comment.py, bot/records.py)

**Files:**
- Create: `bot/comment.py`, `bot/records.py`, `tests/test_comment_records.py`

**Interfaces:**
- Produces:
  - `comment.build(rec: ForecastRecord, max_chars: int) -> str`
  - `records.question_summary(q: MetaculusQuestion) -> QuestionSummary` (maps forecasting-tools question objects; `kind` from `q.get_question_type()` name lowercased; date questions carry epoch seconds bounds)
  - `records.write(rec: ForecastRecord, runs_dir: str = "runs") -> str` writes `runs/<YYYY-MM-DD>/<post_id>_<run_ts_compact>.json`, returns path
  - `records.already_forecasted_locally(post_id: int, runs_dir: str) -> bool`

- [ ] **Step 1: Write the failing tests**

`tests/test_comment_records.py`:
```python
import json
from pathlib import Path
from bot import comment, records
from bot.models import (ForecastRecord, QuestionSummary, Forensics, BlindEstimate, EvidenceTable, Evidence,
                        ForecastValue, MemberForecast, Aggregate)


def _rec():
    q = QuestionSummary(post_id=42, question_id=43, url="https://m/42", title="Will X?", kind="binary", close_time=None, options=None,
                        lower_bound=None, upper_bound=None, open_lower=None, open_upper=None, cdf_size=None, zero_point=None, unit=None)
    return ForecastRecord(
        question=q, run_ts="2026-09-12T10:00:00+00:00", flags={"forensics": True, "devils_advocate": True},
        forensics=Forensics(resolution_statement="Resolves Yes if X by Oct 1.", status_quo_outcome="No"),
        blind=BlindEstimate(reference_class="rc", base_rate_reasoning="br", forecast=ForecastValue(kind="binary", probability=0.2)),
        evidence=EvidenceTable(items=[Evidence(claim="claim one", source="S1", reliability="B", credibility=2, supports="Yes"),
                                      Evidence(claim="claim two", source="S2", reliability="D", credibility=4, supports="No")]),
        members=[MemberForecast(name="a", model="m1", forecast=ForecastValue(kind="binary", probability=0.25), reasoning="x" * 5000),
                 MemberForecast(name="b", model="m2", forecast=ForecastValue(kind="binary", probability=0.3), reasoning="y")],
        aggregate=Aggregate(pre_da=ForecastValue(kind="binary", probability=0.27), post_da=ForecastValue(kind="binary", probability=0.24), method="logit_median", da_critique="crit"),
        final=ForecastValue(kind="binary", probability=0.24), cost_usd=0.31, guards_fired=[], published=False)


def test_comment_contents_and_length():
    c = comment.build(_rec(), 3000)
    assert len(c) <= 3000
    for s in ["Resolves Yes if X by Oct 1.", "0.20", "claim one", "B2", "0.27", "0.24", "Final", "gpt" if False else "a, b"]:
        assert s in c
    assert "x" * 100 not in c  # member reasoning is not dumped into the comment


def test_write_and_local_check(tmp_path):
    rec = _rec()
    p = records.write(rec, runs_dir=str(tmp_path))
    assert Path(p).exists() and "2026-09-12" in p and "42_" in p
    assert json.loads(Path(p).read_text())["final"]["probability"] == 0.24
    assert records.already_forecasted_locally(42, str(tmp_path)) and not records.already_forecasted_locally(7, str(tmp_path))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_comment_records.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write bot/comment.py**

```python
from __future__ import annotations
from bot.models import ForecastRecord, ForecastValue


def _fmt(v: ForecastValue | None) -> str:
    if v is None:
        return "n/a"
    if v.kind == "binary":
        return f"{v.probability:.2f}"
    if v.kind == "multiple_choice":
        return "; ".join(f"{k}: {p:.2f}" for k, p in v.options.items())
    return "; ".join(f"p{k}={val:g}" for k, val in sorted(v.percentiles.items()))


def build(rec: ForecastRecord, max_chars: int) -> str:
    parts = ["**Resolution forensics.** " + (rec.forensics.resolution_statement if rec.forensics else "stage off")]
    if rec.forensics:
        parts.append(f"Status quo: {rec.forensics.status_quo_outcome}. Traps: {'; '.join(rec.forensics.traps[:3]) or 'none noted'}.")
    if rec.blind:
        parts.append(f"**Blind base rate.** {rec.blind.reference_class}. Estimate {_fmt(rec.blind.forecast)}.")
    if rec.evidence and rec.evidence.items:
        top = sorted(rec.evidence.items, key=lambda e: (e.reliability, e.credibility))[:3]
        parts.append("**Key evidence.** " + " | ".join(f"[{e.reliability}{e.credibility}] {e.claim} ({e.source})" for e in top))
    if rec.aggregate:
        names = ", ".join(m.name for m in rec.members if m.dropped_reason is None)
        parts.append(f"**ACH ensemble** ({names}): {_fmt(rec.aggregate.pre_da)} via {rec.aggregate.method}.")
        if rec.aggregate.post_da is not None:
            parts.append(f"**Devil's advocate** moved it to {_fmt(rec.aggregate.post_da)}.")
    parts.append(f"**Final:** {_fmt(rec.final)}")
    flags = ",".join(k for k, v in rec.flags.items() if v)
    parts.append(f"_bot=XtremeSavageForecast stages={flags} cost=${rec.cost_usd:.2f}_")
    text = "\n\n".join(parts)
    if len(text) > max_chars:
        text = text[: max_chars - 15].rstrip() + "\n\n[truncated]"
    return text
```

- [ ] **Step 4: Write bot/records.py**

```python
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from forecasting_tools import MetaculusQuestion, MultipleChoiceQuestion, NumericQuestion, DateQuestion
from bot.models import ForecastRecord, QuestionSummary


def question_summary(q: MetaculusQuestion) -> QuestionSummary:
    kind = q.get_question_type().get_api_type_name()
    lo = hi = zp = None
    open_lo = open_hi = None
    cdf_size = None
    if isinstance(q, DateQuestion):
        lo, hi = q.lower_bound.timestamp(), q.upper_bound.timestamp()
        open_lo, open_hi, zp, cdf_size = q.open_lower_bound, q.open_upper_bound, q.zero_point, q.cdf_size
    elif isinstance(q, NumericQuestion):
        lo, hi = q.lower_bound, q.upper_bound
        open_lo, open_hi, zp, cdf_size = q.open_lower_bound, q.open_upper_bound, q.zero_point, q.cdf_size
    return QuestionSummary(
        post_id=q.id_of_post, question_id=q.id_of_question, url=q.page_url or "", title=q.question_text, kind=kind,
        close_time=q.close_time.isoformat() if q.close_time else None,
        options=q.options if isinstance(q, MultipleChoiceQuestion) else None,
        lower_bound=lo, upper_bound=hi, open_lower=open_lo, open_upper=open_hi, cdf_size=cdf_size, zero_point=zp,
        unit=q.unit_of_measure,
    )


def write(rec: ForecastRecord, runs_dir: str = "runs") -> str:
    ts = datetime.fromisoformat(rec.run_ts)
    day = ts.astimezone(timezone.utc).strftime("%Y-%m-%d")
    compact = ts.astimezone(timezone.utc).strftime("%H%M%S")
    d = Path(runs_dir) / day
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{rec.question.post_id}_{compact}.json"
    p.write_text(rec.model_dump_json(indent=1), encoding="utf-8")
    return str(p)


def already_forecasted_locally(post_id: int, runs_dir: str = "runs") -> bool:
    for p in Path(runs_dir).glob(f"**/{post_id}_*.json"):
        try:
            if json.loads(p.read_text(encoding="utf-8")).get("published"):
                return True
        except (json.JSONDecodeError, OSError):
            continue
    return False
```

Note: `already_forecasted_locally` returns True only for published records, so a dry run does not block a later live run. The test record has `published=False`; adjust the test's `_rec()` to `published=True` before the write assertion if the check fails for that reason (that is the intended semantics).

- [ ] **Step 5: Run tests, fix the `published` expectation, run again**

Run: `.venv/Scripts/python.exe -m pytest tests/test_comment_records.py -v`
Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add bot/comment.py bot/records.py tests/test_comment_records.py
git commit -m "feat: comment builder and run records"
```

---
### Task 10: Pipeline orchestration (bot/pipeline.py)

**Files:**
- Create: `bot/pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 3 to 9.
- Produces:
  - `class Publisher(Protocol)`: `is_open(post_id: int) -> bool`; `publish(q: QuestionSummary, value: ForecastValue, comment: str) -> None`.
  - `class MetaculusPublisher(Publisher)`: wraps `MetaculusClient`. `is_open` re-fetches via `get_question_by_post_id` and checks `state == QuestionState.OPEN` (import from `forecasting_tools.data_models.questions`) and `close_time > now`. `publish` dispatches: binary → `post_binary_question_prediction(question_id, p)`; MC → `post_multiple_choice_question_prediction(question_id, options)`; numeric/discrete/date → build CDF with `aggregate.percentiles_to_cdf` and call `post_numeric_question_prediction(question_id, cdf)`; then `post_question_comment(post_id, comment, is_private=True)`.
  - `async forecast_question(q: MetaculusQuestion, settings: Settings, llm: Llm, publisher: Publisher | None, today: str, runs_dir: str = "runs") -> ForecastRecord`. `publisher=None` means dry run.

Behavior, in order: build `QuestionSummary` and `Budget`; stage 1 (if flag) else a minimal `Forensics` from the criteria text; stage 2 (if flag); stage 3 research + evidence (if flag; research only runs when evidence_table is on); stage 4 members in parallel via `asyncio.gather`, each wrapped so one failure yields a dropped member; guards `drop_invalid_members` and `enough_members` (skip with `SKIP_MIN_MEMBERS`); aggregate; stage 5 unless flag off or `budget.should_skip_da` (guard `DA_SKIPPED_BUDGET`); bound the DA move with `bounded_logit_shift` for binary (for MC and numeric, accept the revision only if `validate_value` passes, else keep pre-DA and record `DA_REVISION_INVALID`); final clamp via `aggregate_binary([p])` for binary; build comment; if publisher: `is_open` else `PUBLISH_SKIPPED_CLOSED`; publish; set `published=True`; on any exception set `rec.error`, guard `PIPELINE_ERROR`; always `records.write`.

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline.py`:
```python
import json
from pathlib import Path
from forecasting_tools import BinaryQuestion
from bot.config import load_settings
from bot import pipeline

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

    def is_open(self, post_id):
        return self.open_

    def publish(self, q, value, comment):
        self.published.append((q.post_id, value, comment))


def _bq():
    return BinaryQuestion(question_text="Will X?", id_of_post=5, id_of_question=6, page_url="https://m/5",
                          background_info="bg", resolution_criteria="crit https://src.example/x", fine_print="fp")


async def test_full_binary_run_with_bounded_da(tmp_path, monkeypatch):
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pipeline.py -v`
Expected: FAIL with `ImportError: cannot import name 'pipeline'`

- [ ] **Step 3: Write bot/pipeline.py**

```python
from __future__ import annotations
import asyncio
import logging
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
        self.c.post_question_comment(q.post_id, comment, is_private=True)


def _stage(rec: ForecastRecord, name: str, model: str, cost: float, t0: float) -> None:
    import time
    rec.stage_costs.append(StageCost(stage=name, model=model, cost_usd=cost, seconds=time.monotonic() - t0))
    rec.cost_usd += cost


async def forecast_question(q: MetaculusQuestion, settings: Settings, llm: Llm, publisher: Publisher | None, today: str, runs_dir: str = "runs") -> ForecastRecord:
    import time
    qs = records.question_summary(q)
    rec = ForecastRecord(question=qs, run_ts=datetime.now(timezone.utc).isoformat(), flags=settings.stages.model_dump())
    budget = Budget(settings.limits.question_wall_clock_s, settings.limits.per_question_usd)
    desc, crit, fine = q.background_info or "", q.resolution_criteria or "", q.fine_print or ""
    try:
        # Stage 1
        t0 = time.monotonic()
        if settings.stages.forensics:
            f, res = await forensics.run(llm, settings, qs, desc, crit, fine, today)
            _stage(rec, "forensics", res.model, res.cost_usd, t0)
        else:
            f = Forensics(resolution_statement=crit[:1500], status_quo_outcome="unknown", search_queries=[qs.title])
        rec.forensics = f
        # Stage 2
        blind = None
        if settings.stages.blind_base_rate:
            t0 = time.monotonic()
            blind, res = await base_rate.run(llm, settings, qs, desc, crit, f, today)
            _stage(rec, "blind_base_rate", res.model, res.cost_usd, t0)
        rec.blind = blind
        # Stage 3
        ev = None
        if settings.stages.evidence_table:
            t0 = time.monotonic()
            bundle, rcost = await research.run(llm, settings, f, crit, desc)
            rec.research = bundle
            _stage(rec, "research", settings.models.web_search, rcost, t0)
            t0 = time.monotonic()
            ev, res = await evidence.run(llm, settings, qs, f, bundle, today)
            _stage(rec, "evidence_table", res.model, res.cost_usd, t0)
        rec.evidence = ev
        # Stage 4
        t0 = time.monotonic()

        async def one(m):
            try:
                return await forecast.run_member(llm, settings, m, qs, desc, crit, fine, f, blind, ev, today)
            except Exception as e:  # noqa: BLE001
                return MemberForecast(name=m.name, model=m.model, forecast=ForecastValue(kind=qs.kind), reasoning="", dropped_reason=f"{type(e).__name__}: {e}")

        members: list[MemberForecast] = list(await asyncio.gather(*(one(m) for m in settings.models.members)))
        rec.members = members
        _stage(rec, "forecast_members", "ensemble", sum(m.cost_usd for m in members), t0)
        survivors = drop_invalid_members([m for m in members if m.dropped_reason is None], qs)
        if not enough_members(survivors, settings.limits.min_members):
            rec.guards_fired.append("SKIP_MIN_MEMBERS")
            return rec
        pre = agg.aggregate([m.forecast for m in survivors], qs, settings.forecast)
        rec.aggregate = Aggregate(pre_da=pre, method="logit_median" if qs.kind == "binary" else ("option_median" if qs.kind == "multiple_choice" else "cdf_pointwise_median"))
        final = pre
        # Stage 5
        if settings.stages.devils_advocate:
            if budget.should_skip_da(rec.cost_usd, settings.limits.da_skip_at_budget_fraction):
                rec.guards_fired.append("DA_SKIPPED_BUDGET")
            else:
                t0 = time.monotonic()
                revised, critique, dcost = await devils_advocate.run(llm, settings, qs, f, ev or EvidenceTable(), pre, today)
                _stage(rec, "devils_advocate", settings.models.forecast_tier, dcost, t0)
                rec.aggregate.da_critique = critique
                if qs.kind == "binary":
                    p = agg.bounded_logit_shift(pre.probability, revised.probability, settings.forecast.da_max_logit_shift)
                    final = ForecastValue(kind="binary", probability=agg.aggregate_binary([p], settings.forecast.p_min, settings.forecast.p_max))
                elif validate_value(revised, qs) == []:
                    final = revised if qs.kind != "multiple_choice" else ForecastValue(kind="multiple_choice", options=agg.aggregate_mc([revised.options], qs.options, settings.forecast.mc_floor))
                else:
                    rec.guards_fired.append("DA_REVISION_INVALID")
                rec.aggregate.post_da = final
        rec.final = final
        rec.comment = comment_mod.build(rec, settings.comment.max_chars)
        # Publish gate
        if publisher is None:
            return rec
        if not publisher.is_open(qs.post_id):
            rec.guards_fired.append("PUBLISH_SKIPPED_CLOSED")
            return rec
        publisher.publish(qs, final, rec.comment)
        rec.published = True
        return rec
    except Exception as e:  # noqa: BLE001
        log.exception("pipeline error on %s", qs.url)
        rec.error = f"{type(e).__name__}: {e}"
        rec.guards_fired.append("PIPELINE_ERROR")
        return rec
    finally:
        if llm is not None and getattr(llm, "fallback_used", False):
            rec.guards_fired.append("PROVIDER_FALLBACK")
        records.write(rec, runs_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pipeline.py -v`
Expected: 4 PASSED. If `BinaryQuestion(...)` in the test needs extra required fields, add them with neutral values in `_bq()`; the pipeline must not depend on them.

- [ ] **Step 5: Run the whole suite and commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all green.

```bash
git add bot/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline orchestration with guards and publish gate"
```

---

### Task 11: CLI entrypoint (run.py)

**Files:**
- Create: `run.py`, `tests/test_run.py`

**Interfaces:**
- Produces: `run.select_questions(questions: list[MetaculusQuestion], max_n: int, runs_dir: str) -> list[MetaculusQuestion]` (drop `already_forecasted`, drop `records.already_forecasted_locally`, sort by `close_time` ascending, take `max_n`); `run.main(argv: list[str] | None = None) -> int` (exit code non-zero when any guard fired or season cap hit).
- CLI: `python run.py --mode {tournament,cup,test,dry} [--tournament ID] [--limit N] [--config config.yaml]`. `tournament` = fall + minibench, publish. `cup` = cup, publish. `test` = testing area, publish. `dry` = `--tournament` (default testing area), no publish.

- [ ] **Step 1: Write the failing test**

`tests/test_run.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_run.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'run'`

- [ ] **Step 3: Write run.py**

```python
from __future__ import annotations
import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
import dotenv
from forecasting_tools import MetaculusClient, MetaculusQuestion
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


def select_questions(questions: list[MetaculusQuestion], max_n: int, runs_dir: str) -> list[MetaculusQuestion]:
    far = datetime.max.replace(tzinfo=timezone.utc)
    keep = [q for q in questions if not q.already_forecasted and not records.already_forecasted_locally(q.id_of_post, runs_dir)]
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
    questions = select_questions(questions, args.limit or s.limits.max_questions_per_run, args.runs_dir)
    log.info("forecasting %d questions (mode=%s)", len(questions), args.mode)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sem = asyncio.Semaphore(s.limits.max_concurrent_questions)
    guards = 0

    async def one(q):
        nonlocal guards
        async with sem:
            rec = await forecast_question(q, s, Llm(s), publisher, today, args.runs_dir)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_run.py -v`
Expected: 2 PASSED

- [ ] **Step 5: First real dry run (needs `.env` with METACULUS_TOKEN, OPENROUTER_API_KEY; AskNews optional)**

Run: `.venv/Scripts/python.exe run.py --mode dry --limit 1`
Expected: one question from bot-testing-area goes through all five stages, a record lands in `runs/<date>/`, nothing is posted, cost under $1. Read the record and the comment by hand; fix prompt or parser problems found before continuing. This is the first step that spends money; confirm with XtremeSavageXD first.

- [ ] **Step 6: Commit**

```bash
git add run.py tests/test_run.py
git commit -m "feat: CLI entrypoint with modes, ordering, and season cap"
```

---
### Task 12: GitHub Actions workflows for our bot

**Files:**
- Create: `.github/workflows/main_bot.yaml`, `.github/workflows/cup.yaml`, `.github/workflows/test_bot.yaml`
- Modify: `README.md` (add a "How to run" section: local dry run, live modes, secrets list, where logs land)

**Interfaces:**
- Consumes: `run.py` CLI from Task 11.
- Produces: scheduled runs that commit `runs/` back to `main`.

Design notes: the workflow needs `contents: write` to push records. Use `git pull --rebase` before pushing because the control bot workflow may have pushed meanwhile (the control bot writes nothing to `runs/`, but keep the rebase anyway). The run step uses `continue-on-error: true` so a non-zero exit (guards fired) still commits the records, then a final step fails the job if the exit code was non-zero, so Actions emails on degradation.

- [ ] **Step 1: Write .github/workflows/main_bot.yaml**

```yaml
name: Main bot on tournament

on:
  workflow_dispatch:
    inputs:
      mode:
        description: "tournament | test | dry"
        default: "tournament"
      limit:
        description: "max questions this run"
        default: "15"
  schedule:
    - cron: "7,27,47 * * * *"

permissions:
  contents: write

concurrency:
  group: ${{ github.workflow }}
  cancel-in-progress: false

jobs:
  forecast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: snok/install-poetry@v1
        with:
          virtualenvs-create: true
          virtualenvs-in-project: true
      - run: poetry install --no-interaction --no-root
      - name: Run bot
        id: run
        continue-on-error: true
        run: |
          poetry run python run.py --mode ${{ github.event.inputs.mode || 'tournament' }} --limit ${{ github.event.inputs.limit || '15' }}
          echo "exit=$?" >> "$GITHUB_OUTPUT"
        env:
          METACULUS_TOKEN: ${{ secrets.METACULUS_TOKEN }}
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          ASKNEWS_CLIENT_ID: ${{ secrets.ASKNEWS_CLIENT_ID }}
          ASKNEWS_SECRET: ${{ secrets.ASKNEWS_SECRET }}
      - name: Commit run records
        run: |
          git config user.name "forecasting-bot"
          git config user.email "bot@users.noreply.github.com"
          git add runs/
          if git diff --cached --quiet; then echo "no records"; exit 0; fi
          git commit -m "runs: $(date -u +%Y-%m-%dT%H:%MZ) mode=${{ github.event.inputs.mode || 'tournament' }}"
          git pull --rebase origin main
          git push origin HEAD:main
      - name: Fail job if guards fired
        if: steps.run.outputs.exit != '0'
        run: echo "bot exited with ${{ steps.run.outputs.exit }} (guards fired or error)"; exit 1
```

Note on `echo "exit=$?"`: with `set -e` default shell, a non-zero exit stops the script before the echo. Prefix the run line with `set +e` on its own line, then `poetry run ...`, then `echo "exit=$?" >> "$GITHUB_OUTPUT"`.

- [ ] **Step 2: Write .github/workflows/cup.yaml**

Same as main_bot.yaml with `name: Main bot on Metaculus Cup`, cron `"0 2 */2 * *"`, no inputs, run line `poetry run python run.py --mode cup --limit 15`, and commit message `runs: ... mode=cup`.

- [ ] **Step 3: Write .github/workflows/test_bot.yaml**

`workflow_dispatch` only, with an input `mode` defaulting to `dry`, run line `poetry run python run.py --mode ${{ github.event.inputs.mode }} --limit 3`, same secrets, same commit step. This is the button for smoke tests.

- [ ] **Step 4: Validate YAML locally**

Run: `.venv/Scripts/python.exe -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yaml')]; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Add "How to run" to README.md**

Append after the Timeline section:

```markdown
## How to run

Local (Python 3.12 venv at `.venv`):

    .venv/Scripts/python.exe -m pytest -q                 # tests, no network
    .venv/Scripts/python.exe run.py --mode dry --limit 1  # full pipeline, no publish
    .venv/Scripts/python.exe run.py --mode test           # publish to bot-testing-area
    .venv/Scripts/python.exe control_bot.py --mode test_questions

GitHub Actions: `Main bot on tournament` every 20 min (Fall + MiniBench), `Main bot on Metaculus Cup` every 2 days, `Control bot` workflows on the same cadence with the control token, `Test bot` manual. Records land in `runs/YYYY-MM-DD/` and are committed automatically.

Secrets (Settings, Secrets and variables, Actions): `METACULUS_TOKEN`, `METACULUS_TOKEN_CONTROL`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `ASKNEWS_CLIENT_ID`, `ASKNEWS_SECRET`.
```

- [ ] **Step 6: Commit**

```bash
git add .github/workflows README.md
git commit -m "ci: workflows for main bot, cup, and manual test with record commits"
```

- [ ] **Step 7: Create the public GitHub repo and push (confirm with XtremeSavageXD first: public from day one was agreed)**

```bash
"/c/Program Files/GitHub CLI/gh.exe" repo create forecasting-bot --public --source . --remote origin --push
```

Then XtremeSavageXD adds the six secrets in the repo settings. Then trigger `Test bot` with mode `dry`. Expected: green run, a new commit `runs: ...` on main containing one record.

---

### Task 13: Score joiner (scores.py)

**Files:**
- Create: `scores.py`, `tests/test_scores.py`

**Interfaces:**
- Produces:
  - `load_records(runs_dir: str) -> list[dict]` (latest published record per post_id)
  - `binary_log_score(p: float, resolved_yes: bool) -> float` = `ln(p)` if yes else `ln(1-p)`
  - `peer_vs_community(p: float, cp: float, resolved_yes: bool) -> float` = `100 * (log_score(p) - log_score(cp))`
  - `join(records: list[dict], fetch: Callable[[int], dict]) -> list[dict]` where `fetch(post_id)` returns `{"resolved": bool, "resolution": str|None, "cp_at_reveal": float|None}`; output rows: post_id, kind, blind_p, pre_da_p, post_da_p, final_p, cp, resolution, log_score_final, log_score_blind, log_score_pre_da, peer_proxy, cost_usd.
  - `metaculus_fetch(client: MetaculusClient) -> Callable[[int], dict]` reads `q.resolution_string` and `q.api_json`; the community prediction at reveal is discovered in Step 4.
  - `main()` writes `runs/scores.csv` and prints a summary table: mean log score by stage (blind / pre-DA / final), mean peer proxy, n resolved, total cost, cost per scored question.

- [ ] **Step 1: Write the failing tests**

`tests/test_scores.py`:
```python
import json, math
import scores


def test_log_and_peer():
    assert scores.binary_log_score(0.8, True) == math.log(0.8)
    assert scores.binary_log_score(0.8, False) == math.log(0.2)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scores.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scores'`

- [ ] **Step 3: Write scores.py**

```python
from __future__ import annotations
import csv
import json
import math
import sys
from pathlib import Path
from typing import Callable
import dotenv
from forecasting_tools import MetaculusClient


def load_records(runs_dir: str) -> list[dict]:
    latest: dict[int, dict] = {}
    for p in sorted(Path(runs_dir).glob("**/*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not r.get("published"):
            continue
        pid = r["question"]["post_id"]
        if pid not in latest or r["run_ts"] > latest[pid]["run_ts"]:
            latest[pid] = r
    return list(latest.values())


def binary_log_score(p: float, resolved_yes: bool) -> float:
    return math.log(p if resolved_yes else 1 - p)


def peer_vs_community(p: float, cp: float, resolved_yes: bool) -> float:
    return 100 * (binary_log_score(p, resolved_yes) - binary_log_score(cp, resolved_yes))


def _p(node: dict | None) -> float | None:
    return None if not node or node.get("probability") is None else float(node["probability"])


def join(records: list[dict], fetch: Callable[[int], dict]) -> list[dict]:
    rows = []
    for r in records:
        if r["question"]["kind"] != "binary":
            continue  # v1 scores binaries only; numeric/MC come from the Metaculus leaderboard
        info = fetch(r["question"]["post_id"])
        if not info.get("resolved") or info.get("resolution") not in ("yes", "no"):
            continue
        yes = info["resolution"] == "yes"
        blind, pre, post, final = _p((r.get("blind") or {}).get("forecast")), _p((r.get("aggregate") or {}).get("pre_da")), _p((r.get("aggregate") or {}).get("post_da")), _p(r.get("final"))
        cp = info.get("cp_at_reveal")
        rows.append({
            "post_id": r["question"]["post_id"], "kind": "binary", "resolution": info["resolution"], "cp": cp,
            "blind_p": blind, "pre_da_p": pre, "post_da_p": post, "final_p": final,
            "log_score_final": binary_log_score(final, yes) if final is not None else None,
            "log_score_blind": binary_log_score(blind, yes) if blind is not None else None,
            "log_score_pre_da": binary_log_score(pre, yes) if pre is not None else None,
            "peer_proxy": peer_vs_community(final, cp, yes) if (final is not None and cp) else None,
            "cost_usd": r.get("cost_usd", 0.0),
        })
    return rows


def metaculus_fetch(client: MetaculusClient) -> Callable[[int], dict]:
    def f(post_id: int) -> dict:
        q = client.get_question_by_post_id(post_id)
        res = (q.resolution_string or "").lower() or None
        cp = None
        try:  # discovered path, see Step 4
            aggs = q.api_json["question"]["aggregations"]["recency_weighted"]["history"]
            cp = float(aggs[-1]["centers"][0]) if aggs else None
        except (KeyError, IndexError, TypeError):
            cp = None
        return {"resolved": res in ("yes", "no"), "resolution": res, "cp_at_reveal": cp}
    return f


def main() -> int:
    dotenv.load_dotenv()
    rows = join(load_records("runs"), metaculus_fetch(MetaculusClient()))
    out = Path("runs/scores.csv")
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["post_id"])
        w.writeheader(); w.writerows(rows)

    def mean(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else float("nan")

    print(f"resolved binaries: {len(rows)}")
    for k in ("log_score_blind", "log_score_pre_da", "log_score_final", "peer_proxy"):
        print(f"{k:18s} mean={mean(k):.4f}")
    print(f"cost per scored question: ${mean('cost_usd'):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Discover the community-prediction path on one real resolved question**

Run (needs `.env`):
```
.venv/Scripts/python.exe -c "from forecasting_tools import MetaculusClient; import json; q=MetaculusClient().get_question_by_post_id(<a resolved binary post id from runs/>); print(q.resolution_string); print(json.dumps(q.api_json['question'].get('aggregations'), indent=1)[:3000])"
```
Adjust `metaculus_fetch` to the actual key layout (the FAQ says spot scores use the value at `cp_reveal_time`; the API exposes aggregation history with timestamps, pick the entry at or just after `q.cp_reveal_time`). Record the final key path in a comment in `scores.py`.

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scores.py -v`
Expected: 2 PASSED

```bash
git add scores.py tests/test_scores.py
git commit -m "feat: score joiner for blind/pre-DA/final comparison"
```

---

### Task 14: Dashboard (after the bot is live)

**Files:**
- Create: `docs/dashboard/index.html`, `docs/dashboard/build_index.py`, `.github/workflows/pages.yaml`

**Interfaces:**
- `build_index.py` reads `runs/**/*.json` and `runs/scores.csv` (if present) and writes `docs/dashboard/data.json`: `{"generated": iso, "records": [slim rows: post_id, url, title, kind, run_ts, final, blind, pre_da, post_da, cost_usd, guards_fired, published], "scores": [rows from csv]}`.
- `index.html`: static page, no build step, fetches `data.json`, renders: a stat row (questions forecast, published, total cost, cost per question, guards fired), a table of recent forecasts with links, and a small calibration table comparing mean log score for blind vs pre-DA vs final when scores exist. Load the `dataviz` skill before writing any chart.
- `pages.yaml`: on push to main, run `build_index.py`, upload `docs/dashboard` as the Pages artifact, deploy.

- [ ] **Step 1: Write build_index.py with a test that runs it against `tests/fixtures` records** (reuse the record shape from `tests/test_scores.py`; assert `data.json` has one record and the stat fields).
- [ ] **Step 2: Write index.html** reading `data.json` (fetch relative path), plain HTML/CSS/JS, theme-aware, phone-width safe.
- [ ] **Step 3: Write pages.yaml** using `actions/configure-pages@v5`, `actions/upload-pages-artifact@v3` with `path: docs/dashboard`, and `actions/deploy-pages@v4`; `permissions: pages: write, id-token: write`.
- [ ] **Step 4: Enable Pages in repo settings (source: GitHub Actions)**, push, open the URL, verify the table renders from live `runs/`.
- [ ] **Step 5: Commit** `feat: static dashboard over run records`.

---

## Self-review against the spec

- Spec 2 (layout): Task 1, 2, 11, 12 cover every file; `bot/logging_.py` in the spec became `bot/records.py` here (same responsibility, clearer name).
- Spec 3 (pipeline stages 1 to 5, aggregation, comment): Tasks 5, 7, 9, 10. Percentile set `[5,10,20,40,60,80,90,95]` matches spec.
- Spec 4 (guards): min members, prose/JSON consistency, bounds, publish gate, dead-provider fallback, time budget (DA skip), cost ceiling (per call in Task 4, per question via Budget), season cap (Task 11), already-forecasted skip (Task 11). Non-zero exit on guards: Task 11 returns 1, Task 12 fails the job after committing.
- Spec 5 (logging, scores, dashboard): Tasks 9, 13, 14. Records committed by workflow in Task 12.
- Spec 6 (cost control): Tasks 4, 6, 11. Cheap tier used for evidence extraction only; forensics, base rate, forecast, DA use forecast tier.
- Spec 7 (testing): every task has offline tests; dry mode in Task 11; live smoke in Tasks 2, 11, 12.
- Spec 8 (operations): Task 2 and 12 workflows, secrets list, concurrency groups.
- Type consistency check: `ForecastValue`, `QuestionSummary`, `MemberForecast`, `Aggregate`, `ForecastRecord` names and fields match across Tasks 3, 5, 6, 7, 9, 10, 13. `Llm.complete` / `complete_json` signatures match between Task 4 and the fakes in Tasks 7 and 10. `records.write(rec, runs_dir)` used identically in Tasks 9 and 10.
- Known deferred items (out of scope per spec section 10): Market Pulse, question-group consistency, prediction-market inputs, numeric/MC self-scoring in `scores.py` (leaderboard covers them).
