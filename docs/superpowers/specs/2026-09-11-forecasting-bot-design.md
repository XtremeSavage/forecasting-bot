# Forecasting Bot: Design Spec

Date: 2026-09-11. Status: approved by XtremeSavageXD 2026-09-11; implemented on branch build/v1 2026-09-12 (all 14 plan tasks reviewed and complete, 58 offline tests). Live status and next steps: docs/HANDOFF.md.
Background: `README.md` (goals, rules) and `docs/RESEARCH.md` (past winners, scoring, Fall 2026 facts).

## 1. Goal

A Metaculus forecasting bot for the Fall 2026 FutureEval Bot Tournament, MiniBench, and the Metaculus Cup, built as a simple, guarded pipeline with a small number of intelligence-analysis techniques applied rigorously, plus a measurement harness that can show whether each technique helps.

Success at end of season:
- Positive total peer score (prize-eligible).
- Top 10 of the field (stretch).
- A measured answer to "did the tradecraft layer beat the unmodified template," from a live control bot.

Decisions already made (see README for the question round):
- Arenas: Fall main tournament, MiniBench, Metaculus Cup from day one. Market Pulse after the main bot is stable.
- Public repo from day one. Python. GitHub Actions hosting.
- Final-forecast model: GPT-5.x via OpenRouter. Claude in the ensemble. Anthropic direct keys as fallback.
- Research: AskNews, OpenRouter web search, direct fetch of the resolution source.
- Budget: $1 per question, $500 per season, enforced in code.
- Tradecraft v1: resolution forensics, blind base rate, graded evidence table, ACH-lite with status quo as null, devil's advocate.
- Comment format: minimal reasoning trace.
- Control bot: unmodified Metaculus template, separate bot account (XtremeSavageForecast-v2).
- Dashboard: after the bot is live, before Sep 28.
- Autonomy: C. Claude has free rein on code and local files; confirms before spending money, sending messages, or the first submission to a live tournament.

## 2. Repository layout

```
forecasting-bot/
  README.md                 project brief (existing)
  docs/RESEARCH.md          research (existing)
  docs/superpowers/specs/   this spec, later plans
  control_bot.py            Metaculus template main.py, verbatim, never edited
  run.py                    entrypoint for our bot: --mode {tournament,cup,test,dry} --flags
  bot/
    config.py               dataclass of flags, models, clamps, caps; loaded from config.yaml + env
    pipeline.py             orchestrates stages for one question, enforces time and cost budgets
    stages/
      forensics.py          stage 1
      base_rate.py          stage 2
      research.py           stage 3a: AskNews, web search, resolution-source fetch
      evidence.py           stage 3b: evidence table extraction
      forecast.py           stage 4: ACH-lite forecaster, run per ensemble member
      devils_advocate.py    stage 5
    aggregate.py            logit median, MC normalization, CDF pointwise median
    guards.py               all publish guards
    comment.py              builds the private comment
    llm.py                  thin wrapper: model routing, fallback, cost tracking, structured output
    logging_.py             per-question JSON records
  scores.py                 pulls resolved scores + community prediction, joins with runs/
  runs/                     JSON logs committed by the workflow, one file per question per run
  tests/                    pytest; fixtures/ holds recorded stage outputs
  .github/workflows/
    main_bot.yaml           every 20 min on Fall + MiniBench
    control_bot.yaml        every 20 min on Fall + MiniBench, control token
    cup.yaml                both bots on Metaculus Cup every 2 days
    test.yaml               manual, testing area, dry-run
  config.yaml               default flags and model roster
  pyproject.toml            Poetry, Python ^3.11
  .env.template
```

forecasting-tools is used only for: `MetaculusClient` (fetch questions, post predictions, post comments), question classes, `NumericDistribution` and `Percentile`, and `MonetaryCostManager` if it fits. Everything else is ours.

## 3. Pipeline

`pipeline.run(question) -> ForecastRecord | Skip`. Stages run in order; each has a flag in config. Every stage returns a typed dataclass and its raw LLM output is stored in the record.

### Stage 1: Resolution forensics (`forensics.py`)
- Input: title, description, resolution criteria, fine print, resolution source URLs, open/close/resolve dates, question type and options/bounds.
- Output `Forensics`: `resolution_statement` (one paragraph, precise), `status_quo_outcome`, `key_dates`, `traps` (list; e.g. "before X" is forward-looking, "as of" is a snapshot, annulment conditions), `possibly_already_resolved` (bool + why), `search_queries` (3-6 strings), `things_that_do_not_count`.
- Model: frontier (forecast-tier). One call.

### Stage 2: Blind base rate (`base_rate.py`)
- Input: question text and forensics. No research.
- Output `BlindEstimate`: `reference_class`, `base_rate_reasoning`, `blind_forecast` (probability, option distribution, or percentiles by type).
- Model: forecast-tier. One call. Stored as the outside view and as the "no research" control.

### Stage 3a: Research (`research.py`)
- Runs in parallel, each provider isolated with its own timeout; a failed provider yields an empty result and a diagnostic, never an exception:
  - AskNews: news search using forensics queries.
  - OpenRouter web search: a search-enabled model call per query, returning cited snippets.
  - Resolution-source fetch: HTTP GET of each resolution URL, text extracted (trafilatura or similar), truncated.
- Output `ResearchBundle`: list of `RawSource` (provider, url, title, published date, text) plus `diagnostics`.

### Stage 3b: Evidence table (`evidence.py`)
- Input: forensics + research bundle.
- Output `EvidenceTable`: list of `Evidence` items: `claim`, `source`, `date`, `reliability` (A-F, source track record), `credibility` (1-6, plausibility of this specific claim), `supports` (outcome or "context"), `note`. Plus `already_resolved_signal` (evidence the event already happened).
- Model: cheap-tier. One call, structured output.

### Stage 4: ACH-lite forecast (`forecast.py`), N members
- Input: forensics, blind estimate, evidence table, question type details, today's date.
- Prompt structure: hypotheses (status quo is H0), evidence-vs-hypothesis consistency table, what must change for a non-status-quo outcome, time remaining, then the forecast. The prompt states the Metaculus convention: assume the event has not happened unless the evidence says it has.
- Output `MemberForecast`: `reasoning` (text), `forecast` (JSON block: probability / option probabilities / percentiles 5,10,20,40,60,80,90,95), `stated_number_in_prose` (parsed from text for the consistency guard).
- Members: from config roster. Default: GPT-5.x at two temperatures, Claude, one more frontier model. Each via OpenRouter; Anthropic direct as fallback for the Claude member.

### Aggregation (`aggregate.py`)
- Binary: median of logits, back to probability, clamp to `[p_min, p_max]` (default 0.01-0.99).
- Multiple choice: per-option median, floor each at 0.01, renormalize to 1.
- Numeric and date: each member's percentiles to a monotone CDF on the platform's grid (via `NumericDistribution`), pointwise median across members, validated against open/closed bounds; open tails kept at or above a small floor.
- Output `Aggregate` with `pre_da_forecast`.

### Stage 5: Devil's advocate (`devils_advocate.py`)
- Input: forensics, evidence table, aggregate.
- Call 1 (critic): argue the strongest case that the aggregate is wrong. Output `critique`.
- Call 2 (adjudicator): given aggregate and critique, output a revised forecast. Revision bounded: binary moves at most `da_max_logit_shift` (default 0.5 logits); MC and numeric analogous bounds. Both `pre_da_forecast` and `post_da_forecast` are logged.
- Model: forecast-tier.

### Comment (`comment.py`)
Under 3,000 characters: forensics resolution statement, status quo, blind base rate, top three evidence items with grades, ACH verdict in two sentences, DA note in one sentence, final forecast, and a one-line footer listing the flags and members used. Posted as a private comment.

## 4. Guards (`guards.py`)

| Guard | Rule | On failure |
|---|---|---|
| Min members | at least 2 valid member forecasts | skip question, log `SKIP_MIN_MEMBERS` |
| Prose/JSON consistency | member's JSON number within tolerance of number stated in reasoning | drop that member |
| Bounds | numeric CDF monotone, within platform limits, respects closed bounds; MC sums to 1 | fix if mechanical (renormalize), else drop member |
| Publish gate | re-fetch question state immediately before POST; must be open | skip publish, log `PUBLISH_SKIPPED_CLOSED` |
| Dead provider | all OpenRouter calls in a run fail | switch to Anthropic direct for the run, log `PROVIDER_FALLBACK` |
| Time budget | per-question wall clock (default 600 s); questions sorted by close time ascending | at 70% of budget, skip DA; at 100%, publish what exists if min members met |
| Cost ceiling | per-call max and per-question max ($1) | drop to fewer members; never skip publish solely for cost if min members met |
| Season cap | $500 cumulative from `runs/` | bot exits without forecasting, logs `SEASON_CAP` |
| Already forecasted | skip questions with an existing forecast from this bot | skip |

A run exits non-zero if any guard fired, so Actions emails on degradation, not just crashes.

## 5. Logging and measurement

- One JSON file per question per run: `runs/YYYY-MM-DD/<question_id>_<run_ts>.json` containing question metadata, every stage's typed output and raw text, every member forecast, aggregate, pre/post DA, cost by call, timings, flags, guards fired, provider diagnostics.
- The workflow commits `runs/` back to the repo after each run. Public by design.
- `scores.py`: pulls this bot's and the control bot's resolved scores and the revealed community prediction via the Metaculus API, joins with `runs/`, writes `runs/scores.parquet` (or CSV) and a summary. Enables: main vs control, blind vs researched, pre-DA vs post-DA, per-question-type breakdown, cost per scored question.
- Dashboard: static GitHub Pages site reading the JSON and score files. Built after the bot is live.

## 6. Cost control

- `llm.py` wraps every call with a cost estimate from token counts and a price table; refuses calls over the per-call ceiling.
- Tiers in config: `forecast_tier` (frontier), `cheap_tier` (parsing, evidence extraction). Forensics, base rate, forecast, and DA use forecast tier; evidence extraction uses cheap tier.
- Per-question and season caps enforced as in the guard table.

## 7. Testing

- Pytest, no network: aggregation math (logit median, MC normalize, CDF median and bounds), parsers, every guard, comment length, config loading.
- Stage tests using recorded fixtures (real LLM outputs saved once) so prompts and parsers are exercised offline.
- `run.py --mode dry` runs the full pipeline on the testing area and on a small set of resolved questions without publishing; output inspected by hand. Backtests are treated as smoke tests only, because retrieval leaks answers.
- Live smoke test on the testing area, then Metaculus Cup, before any FutureEval tournament.

## 8. Operations

- GitHub Actions, Python 3.11, Poetry. Concurrency group per workflow, `cancel-in-progress: false`.
- Secrets: `METACULUS_TOKEN`, `METACULUS_TOKEN_CONTROL`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `ASKNEWS_CLIENT_ID`, `ASKNEWS_SECRET`.
- Tournament targets from config: Fall `33121` / `fall-futureeval-2026`, MiniBench `minibench`, testing area `32977`, Metaculus Cup current ID from the client.
- Security: keys only in GitHub secrets and a gitignored `.env`; per-key spend limits set on OpenRouter; nothing from XtremeSavageXD's work environment enters the repo.

## 9. Schedule

- **Sep 12 to 13:** repo, control bot forecasting on the testing area, secrets wired. XtremeSavageXD: OpenRouter, AskNews, Discord, participation form.
- **Sep 14 to 18:** pipeline, guards, tests, dry runs. Go live on the testing area and Metaculus Cup the moment it passes.
- **Sep 19 to 20:** buffer and polish.
- **Sep 21:** warmup MiniBench, both bots live. Dashboard built during this week.
- **Sep 28:** Fall tournament opens. Iterate every two weeks on MiniBench results, one change at a time.

## 10. Out of scope for v1

Market Pulse, question-group consistency, prediction-market inputs, agentic multi-step research loops, any post-hoc calibration multiplier, automated messaging.
