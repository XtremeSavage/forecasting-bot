# Handoff: where things stand

Written 2026-09-12 at the end of an overnight autonomous build session. The project now lives at `~/projects/forecasting-bot`; the OneDrive Desktop copy is stale. Read this first in the next session. The README holds goals and rules; `docs/RESEARCH.md` holds the tournament research; the spec and plan live under `docs/superpowers/`.

## One-paragraph status

The bot is built, reviewed, and tested offline, and has never made a paid or live call. Branch `build/v1` holds 28 commits on top of the docs-only base and has been merged to `main`. 89 pytest tests pass with zero warnings. Every piece of the spec exists: config, typed records, LLM wrapper with exact OpenRouter cost accounting and Anthropic fallback, aggregation math, guards and budgets, five tradecraft stages, research providers, comment builder, run records, the pipeline with a publish gate, the CLI, the unmodified Metaculus template as a control bot, GitHub Actions workflows for both bots, a score joiner, and a static dashboard. What has not happened: no dry run against a real question, no live submission, no GitHub secrets, no Pages enabled. Those are gated on XtremeSavageXD.

## What to do next, in order

0. **Push the real branches (2 minutes, XtremeSavageXD).** The repo https://github.com/XtremeSavage/forecasting-bot exists and is public, but the GitHub CLI token was created without the `workflow` scope, so GitHub rejected every push that contains `.github/workflows/`. Only a backup branch `snapshot-no-workflows` made it up. Fix from the project folder, in the Claude Code prompt:
   ```
   ! "C:\Program Files\GitHub CLI\gh.exe" auth refresh -h github.com -s workflow
   ! git push -u origin main
   ! git push -u origin build/v1
   ```
   Then delete the snapshot branch on GitHub. Nothing else in this list works until `main` is on GitHub.

1. **Accounts (XtremeSavageXD).** OpenRouter key with a spend limit. AskNews registration for the bot email. Second Metaculus bot account `XtremeSavageForecast-v2` for the control bot and its token. Metaculus participation form (3 questions, also the credit request). Discord `build-a-forecasting-bot`.
2. **Secrets (XtremeSavageXD).** In the GitHub repo: `METACULUS_TOKEN`, `METACULUS_TOKEN_CONTROL`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `ASKNEWS_CLIENT_ID`, `ASKNEWS_SECRET`. Locally, copy `.env.template` to `.env` and fill it in. Never paste keys into chat.
3. **Before the dry run**, add `workflow_dispatch:` to `.github/workflows/control_cup.yaml` (see residuals below).
4. **First paid dry run (with XtremeSavageXD's go).** From the project folder:
   ```
   .venv/Scripts/python.exe run.py --mode dry --limit 1
   ```
   Expected: one bot-testing-area question flows through all five stages, a record lands in `runs/<date>/`, nothing is posted, cost well under $1. Read the record and the comment by hand. Things to check on that first run, because no test could: the OpenRouter `usage.cost` field actually comes back (otherwise cost shows 0), the `:online` web-search model returns cited text, AskNews returns articles, the resolution-source fetch works on a real URL, the four member models all parse (watch `dropped_reason`), and the devil's advocate revision parses.
5. **Verify the community-prediction key path** in `scores.py` `metaculus_fetch` against one resolved binary question (command is in the plan, Task 13 Step 4). Until then `cp_at_reveal` may be None and `peer_proxy` empty.
6. **Live on the testing area**: `run.py --mode test` locally or the `Test bot` workflow with mode `test`. Then the control bot's `test_questions` workflow. Confirm both bots' forecasts and private comments appear on their profiles.
7. **Enable GitHub Pages** (Settings, Pages, source: GitHub Actions) so the dashboard deploys from `docs/dashboard/`.
8. **Sep 21**: warmup MiniBench. Set the repository variable `BOT_LIVE` to `true` (Settings, Secrets and variables, Actions, Variables); until then the scheduled workflows are inert. Both `Main bot on tournament` and `Control bot` workflows then run every 20 minutes. Watch the first few Actions runs; a run exits non-zero when any guard fires, which emails XtremeSavageXD.
9. **Sep 28**: Fall tournament opens. Same workflows, no change needed; the tournament ID 33121 is in `config.yaml`.

## How the code is laid out

| Path | Purpose |
|---|---|
| `run.py` | CLI. `--mode tournament` (Fall + MiniBench, publish), `cup`, `test` (testing area, publish), `dry` (no publish). Exit 0 clean, 1 if any guard fired, 2 if the $500 season cap is hit. |
| `bot/pipeline.py` | One question end to end. `forecast_question(q, settings, llm, publisher, today, runs_dir)`. `MetaculusPublisher` posts and re-checks the question is open first. |
| `bot/stages/` | `forensics`, `base_rate`, `evidence`, `forecast` (ACH, one call per ensemble member), `devils_advocate`, `research` (AskNews, OpenRouter web search, resolution-URL fetch), `common` (shared prompt pieces and JSON parsing). |
| `bot/llm.py` | OpenRouter via the openai SDK with `usage.include` for exact cost; on any OpenRouter failure the call falls back to `models.anthropic_fallback` via the Anthropic SDK; per-call cost ceiling. |
| `bot/aggregate.py` | Logit median for binary, per-option median with floor for MC, pointwise CDF median for numeric via forecasting-tools' `NumericDistribution`. `bounded_logit_shift` limits the devil's-advocate move. |
| `bot/guards.py` | Member validation and prose/JSON consistency, `Budget`, `season_spent`. |
| `bot/records.py`, `bot/comment.py` | One JSON record per question per run under `runs/`; the private comment (under 3,000 chars, Final line always kept). |
| `config.yaml` | Stage on/off flags, model roster, limits, clamps, tournament IDs. Change models here, not in code. |
| `control_bot.py`, `bot_helpers.py` | Byte-identical copies of the Metaculus template. Never edit. Runs under the control token. |
| `scores.py` | Joins published records with resolutions; writes `runs/scores.csv`; prints mean log scores for blind vs pre-DA vs final. |
| `docs/dashboard/` | `build_index.py` makes `data.json` from `runs/`; `index.html` renders it. Deployed by `pages.yaml`. |
| `.github/workflows/` | `main_bot`, `cup`, `test_bot` (ours), `control_bot`, `control_cup` (template), `pages`. Our workflows commit `runs/` back to `main` after each run. |

Model roster in `config.yaml` as of 2026-09-12 (all verified to exist on OpenRouter): forecast tier `openai/gpt-5.4`; members `openai/gpt-5.4` at two temperatures, `anthropic/claude-sonnet-4.6`, `x-ai/grok-4.6`; cheap tier `openai/gpt-5.4-mini`; web search `openai/gpt-5.4-mini:online`. Rough cost estimate is $0.35 to $0.45 per question against a $1 cap.

## Decisions made without XtremeSavageXD (rulings)

Every ruling is also in the build ledger. The ones that matter:

- Branch `build/v1` in place rather than a separate worktree. Merge to `main` before the workflows will do anything, since they push to `main`.
- Dependency pins follow what pip actually installed (anthropic 1.5.0, httpx 0.28.1, trafilatura 2.2.0, pyyaml 6.0.3, pytest 9.1.1, pytest-asyncio 1.4.0) rather than the plan's guesses.
- `aggregate_mc` drops the floor entirely when floor times option count would exceed 1, so the output always sums to 1.
- `extract_json` takes the whole fenced block first, because stage outputs are nested JSON.
- The pipeline gates stage 4 on `stages.ach_forecast` (off means no forecast, guard `SKIP_ACH_OFF`), reconciles cost against the LLM wrapper's running total so failed calls still count, only flags `PROVIDER_FALLBACK` when the fallback happened during that question, and treats a devil's-advocate failure as `DA_FAILED` while keeping the pre-DA number.
- A dry-run record does not count as "already forecasted"; only published records do.
- `season_spent` ignores malformed files instead of crashing.
- `scores.py` clamps probabilities to Metaculus's 0.001 to 0.999 before taking logs.
- The dashboard only links titles whose URL starts with http or https.
- Paid runs, live triggers, and the community-prediction discovery step were all deferred to XtremeSavageXD.

## Known gaps

- `MetaculusPublisher`, `HttpTransport` (both OpenRouter and Anthropic), AskNews, and the `:online` search have no tests; they can only be exercised by the first paid run.
- The `anthropic` SDK 1.5.0 has no `temperature` argument on `messages.create`; it is passed via `extra_body`. Confirm on the first fallback.
- The community-prediction key path in `scores.py` is a guess marked UNVERIFIED.
- Numeric and multiple-choice questions have never been run end to end against the real API. The testing area has one of each type; check those records closely.
- `control_cup.yaml` has no manual trigger (see residuals).
- Market Pulse, question-group consistency, and prediction-market inputs are out of scope for v1 by design.

## Where the process artifacts are

- Spec: `docs/superpowers/specs/2026-09-11-forecasting-bot-design.md`
- Plan: `docs/superpowers/plans/2026-09-11-forecasting-bot.md`
- Build ledger with every ruling, review verdict, and deferred minor: `docs/superpowers/ledger-2026-09-12.md`.

## Final whole-branch review and fix wave

A senior review of the whole branch found one Critical and ten Important issues; all were fixed in four commits and re-reviewed clean. Test count went from 58 to 89. The headline fixes:

- **Per-question timeout** in `run.py` (`limits.question_wall_clock_s`, default 600 s). Before this, an open-bounded numeric question could hang a whole Actions run with no record written.
- **Numeric percentile read-back** no longer collapses onto the bound; the aggregate is validated and trial-converted to a CDF before publishing (`AGGREGATE_INVALID` guard); a single member whose distribution cannot be built is dropped instead of killing the question.
- **Stage isolation**: forensics, blind base rate, and evidence each fail soft (`FORENSICS_FAILED`, `BLIND_FAILED`, `EVIDENCE_FAILED`) and the question continues.
- **Budget**: roster trimmed to the minimum members when spend nears the cap (`MEMBERS_TRIMMED_BUDGET`); DA skipped when exhausted (`BUDGET_EXHAUSTED`).
- **Provider fallback** now covers every model: if OpenRouter fails, the call goes to `models.anthropic_fallback` directly.
- **Research** queries run concurrently with per-query timeouts; partial results are kept; `NO_RESEARCH` guard when nothing came back.
- **Prompt-injection framing**: fetched source bodies are fenced and declared untrusted in the evidence prompt.
- **Devil's advocate bounded** for MC (per-option logit shift) and numeric (`forecast.da_max_numeric_fraction` of the p10-p90 spread).
- **Date questions are skipped** (`SKIP_DATE_UNSUPPORTED`). Fall 2026 uses no date questions; the Metaculus Cup might.
- **Scheduled workflows are gated** on the repository variable `BOT_LIVE == 'true'`. Merging to main does not start the bot. Manual `workflow_dispatch` runs still work.
- Minor: comment always fits, `FINAL: 45%` no longer misparsed on percent-unit numeric questions, a failed comment post after a successful prediction is recorded as published with `COMMENT_FAILED`.

Residuals parked for XtremeSavageXD, none blocking:

- `control_cup.yaml` has no manual trigger, so it cannot be rehearsed by hand before `BOT_LIVE` is set. One-line fix: add `workflow_dispatch:` under `on:`.
- The control workflows do not pass `ANTHROPIC_API_KEY`; the stock template has no fallback route. XtremeSavageXD's call whether the control should get one.
- During an OpenRouter outage all four ensemble members become the same Anthropic model; `PROVIDER_FALLBACK` records it.
- A timed-out question's record shows `published=False` with no guard string (the guard is only logged); the question is retried next run.
- Web search can fan out to 15 concurrent calls (5 queries times 3 questions); watch spend on the first real run.
- Guard noise: `run.py` exits non-zero on any guard, including routine ones like `PUBLISH_SKIPPED_CLOSED`, so many Actions runs will show red. Consider splitting routine from degradation guards after the first MiniBench round.
- Re-forecasting: the bot forecasts each question once. Spot scoring rewards the forecast standing at community-prediction reveal, so an update pass near close is a plausible later improvement.

The full ledger of rulings and review verdicts is `docs/superpowers/ledger-2026-09-12.md`; the fix brief is `docs/superpowers/final-fix-brief-2026-09-12.md`.
