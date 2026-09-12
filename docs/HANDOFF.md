# Handoff: where things stand

Written 2026-09-12 at the end of an overnight autonomous build session. Read this first in the next session. The README holds goals and rules; `docs/RESEARCH.md` holds the tournament research; the spec and plan live under `docs/superpowers/`.

## One-paragraph status

The bot is built, reviewed, and tested offline, and has never made a paid or live call. Branch `build/v1` holds 23 commits on top of the docs-only `master`. 58 pytest tests pass with zero warnings. Every piece of the spec exists: config, typed records, LLM wrapper with exact OpenRouter cost accounting and Anthropic fallback, aggregation math, guards and budgets, five tradecraft stages, research providers, comment builder, run records, the pipeline with a publish gate, the CLI, the unmodified Metaculus template as a control bot, GitHub Actions workflows for both bots, a score joiner, and a static dashboard. What has not happened: no dry run against a real question, no live submission, no GitHub secrets, no Pages enabled. Those are gated on XtremeSavageXD.

## What to do next, in order

1. **Accounts (XtremeSavageXD).** OpenRouter key with a spend limit. AskNews registration for the bot email. Second Metaculus bot account `XtremeSavageForecast-v2` for the control bot and its token. Metaculus participation form (3 questions, also the credit request). Discord `build-a-forecasting-bot`.
2. **Secrets (XtremeSavageXD).** In the GitHub repo: `METACULUS_TOKEN`, `METACULUS_TOKEN_CONTROL`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `ASKNEWS_CLIENT_ID`, `ASKNEWS_SECRET`. Locally, copy `.env.template` to `.env` and fill it in. Never paste keys into chat.
3. **First paid dry run (with XtremeSavageXD's go).** From the project folder:
   ```
   .venv/Scripts/python.exe run.py --mode dry --limit 1
   ```
   Expected: one bot-testing-area question flows through all five stages, a record lands in `runs/<date>/`, nothing is posted, cost well under $1. Read the record and the comment by hand. Things to check on that first run, because no test could: the OpenRouter `usage.cost` field actually comes back (otherwise cost shows 0), the `:online` web-search model returns cited text, AskNews returns articles, the resolution-source fetch works on a real URL, the four member models all parse (watch `dropped_reason`), and the devil's advocate revision parses.
4. **Verify the community-prediction key path** in `scores.py` `metaculus_fetch` against one resolved binary question (command is in the plan, Task 13 Step 4). Until then `cp_at_reveal` may be None and `peer_proxy` empty.
5. **Live on the testing area**: `run.py --mode test` locally or the `Test bot` workflow with mode `test`. Then the control bot's `test_questions` workflow. Confirm both bots' forecasts and private comments appear on their profiles.
6. **Enable GitHub Pages** (Settings, Pages, source: GitHub Actions) so the dashboard deploys from `docs/dashboard/`.
7. **Sep 21**: warmup MiniBench. Both `Main bot on tournament` and `Control bot` workflows run every 20 minutes automatically once secrets exist. Watch the first few Actions runs; a run exits non-zero when any guard fires, which emails XtremeSavageXD.
8. **Sep 28**: Fall tournament opens. Same workflows, no change needed; the tournament ID 33121 is in `config.yaml`.

## How the code is laid out

| Path | Purpose |
|---|---|
| `run.py` | CLI. `--mode tournament` (Fall + MiniBench, publish), `cup`, `test` (testing area, publish), `dry` (no publish). Exit 0 clean, 1 if any guard fired, 2 if the $500 season cap is hit. |
| `bot/pipeline.py` | One question end to end. `forecast_question(q, settings, llm, publisher, today, runs_dir)`. `MetaculusPublisher` posts and re-checks the question is open first. |
| `bot/stages/` | `forensics`, `base_rate`, `evidence`, `forecast` (ACH, one call per ensemble member), `devils_advocate`, `research` (AskNews, OpenRouter web search, resolution-URL fetch), `common` (shared prompt pieces and JSON parsing). |
| `bot/llm.py` | OpenRouter via the openai SDK with `usage.include` for exact cost; Anthropic direct fallback for `anthropic/` models; per-call cost ceiling. |
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
- The `cup.yaml` workflow has no manual trigger.
- Market Pulse, question-group consistency, and prediction-market inputs are out of scope for v1 by design.

## Where the process artifacts are

- Spec: `docs/superpowers/specs/2026-09-11-forecasting-bot-design.md`
- Plan: `docs/superpowers/plans/2026-09-11-forecasting-bot.md`
- Build ledger with every ruling, review verdict, and deferred minor: `.superpowers/sdd/2026-09-11-forecasting-bot/progress.md` (git-ignored, local only; it was copied to `docs/superpowers/ledger-2026-09-12.md` at the end of the session so it survives the folder move).

## Final whole-branch review

(filled in at the end of the session; see the section below)
