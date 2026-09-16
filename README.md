# Forecasting Bot — Project Brief

Started 2026-09-10. XtremeSavageXD's first project with Claude Code. This file is the single source of truth for what we're building and why. Read it in full before doing any work in this folder. `docs/RESEARCH.md` holds the detailed research on past winners, rules, scoring, and Fall 2026 facts.

## Goal

Build an AI forecasting bot and enter it in the Metaculus FutureEval bot tournaments. Three outcomes we care about, in order:

1. **A competitive, prize-eligible bot** on the Fall 2026 main tournament ($50k pool) and the bi-weekly MiniBench ($1k per round).
2. **A public scoreboard credential in the AI space.** XtremeSavageXD is an analyst who wants a way into AI work that uses analyst skills rather than fighting them. A ranked bot is proof of work that doesn't depend on a resume.
3. **A genuine test of a hypothesis:** does structured analytic tradecraft (source reliability weighting, base rates, key assumptions checks, analysis of competing hypotheses, explicit confidence) make an LLM forecaster measurably better calibrated? If yes, that's a publishable finding.

## Why this project

- XtremeSavageXD's edge is reasoning under uncertainty, source evaluation, and synthesis. Winning bots so far are built by engineers and differ mainly in model choice, research plumbing, and ensembling. None of the *past winners* used analytic tradecraft. Several Fall 2026 entrants plan to (Heuer-inspired, CIA Red Cell-inspired, OSINT centaur; see docs/RESEARCH.md section 6), but as single-technique bolt-ons. The opportunity is a coherent, tested tradecraft pipeline, not the idea alone.
- Fits XtremeSavageXD's schedule. The bot runs itself on GitHub Actions; XtremeSavageXD checks results when free. Tournament rules *require* no human in the loop, so semi-autonomy isn't a compromise, it's the format.
- Near-zero cost. Entry is free. LLM credits are donated by Anthropic, Google, and OpenAI via OpenRouter. AskNews gives bot accounts a free news allocation.
- High floor. The unmodified Metaculus template bot placed 18th of 173 in Spring 2026. Even a rough custom layer starts from a competitive baseline.

## Timeline (confirmed 2026-09-11, see docs/RESEARCH.md)

- **Sep 21 (Mon), 00:00 UTC: warmup MiniBench opens.** First real questions we can score against. Most MiniBench questions land in the first few days.
- **Sep 28 (Mon): Fall tournament questions start opening.** Slow for the first 1-2 weeks, then full pace.
- Questions keep opening until a few weeks before Jan 1, 2027.

Plan (status 2026-09-12: code complete and reviewed, nothing run live yet; see `docs/HANDOFF.md`):

- ~~Now to Sep 20: accounts, secrets, first paid dry run, then live on the testing area.~~ Done 2026-09-13: both bots have posted to bot-testing-area.
- **Sep 21 to Sep 27: warmup MiniBench.** Both bots live. Fix what the first real records reveal. Enable the dashboard.
- **Sep 28 onward: Fall tournament.** Analyze MiniBench results every two weeks, change one thing at a time, keep the control bot untouched.

## How to run

Local (Python 3.12 venv at `.venv`):

```
.venv/Scripts/python.exe -m pytest -q                 # tests, no network
.venv/Scripts/python.exe run.py --mode dry --limit 1  # full pipeline, no publish
.venv/Scripts/python.exe run.py --mode dry --limit 1 --config config.lean.yaml  # same, lean cost profile
.venv/Scripts/python.exe run.py --mode test           # publish to bot-testing-area
.venv/Scripts/python.exe control_bot.py --mode test_questions
```

Two cost profiles ship: `config.yaml` (default, ~$0.40/question) and `config.lean.yaml` (~$0.12-0.15/question, two ensemble members, mini model for the support stages). On GitHub, set the repository variable `BOT_CONFIG` to `config.lean.yaml` to switch; unset means default.

Experiment flag: `forecast.members_see_blind` (default `true`). Set to `false` to withhold the blind base-rate stage's output from the ensemble members; the stage still runs and is recorded. Added 2026-09-16 for the second MiniBench round; see `docs/HANDOFF.md` step 8b.

Scheduled runs are off until the repo variable `BOT_LIVE` is `true` (Settings, Secrets and variables, Actions, Variables). Until then only manual `Run workflow` dispatches do anything.

GitHub Actions: `Main bot on tournament` every 20 min (Fall + MiniBench), `Main bot on Metaculus Cup` every 2 days, `Control bot` workflows on the same cadence with the control token, `Test bot` manual. Records land in `runs/YYYY-MM-DD/` and are committed automatically.

Secrets (Settings, Secrets and variables, Actions): `METACULUS_TOKEN`, `METACULUS_TOKEN_CONTROL`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `ASKNEWS_CLIENT_ID`, `ASKNEWS_SECRET` (or a single `ASKNEWS_API_KEY` instead of the pair).

## Background research (as of 2026-09-10)

### Tournament facts

| Item | Detail |
|---|---|
| Main tournament | $50k pool, 3 seasons/year (Jan, May, Sep starts), ~4 months, 300–500 questions |
| MiniBench | $1k per round, new round every other Monday, ~60 questions, fully automated question creation and resolution |
| Other | Market Pulse tournament ($7k). ~$175k/year in prizes across everything |
| Formats | Binary, numeric, discrete, multiple-choice |
| Question release | Batches of up to 5 at random times; each open ~1.5 hours. This is why the bot runs every 20 min |
| Scoring | Spot peer score, log-based proper scoring rule. Only the last forecast counts. Confident-and-wrong is punished hard; calibration wins |
| Entry cost | Free |
| Credits | Donated LLM credits via OpenRouter (form on the resources page). AskNews: 1,000 calls/month, 4,000/tournament, 5M tokens. Competitive bots spend ~$1–1.50 per question |

### Registration steps

1. Create a normal Metaculus account.
2. Settings, then "My Forecasting Bots", then "Create a Bot."
3. Copy the generated API key (METACULUS_TOKEN).
4. Submit the free-credits form. Get an OpenRouter key.
5. Register the bot's email with AskNews for the free allocation.
6. Join the Metaculus Discord, channel `build-a-forecasting-bot`.

### Template bot

- Repo: https://github.com/Metaculus/metac-bot-template (built on https://github.com/Metaculus/forecasting-tools)
- Fork, add METACULUS_TOKEN and OPENROUTER_API_KEY as GitHub secrets, enable Actions. It then runs every 20 minutes on the live tournament with no hosting.
- Custom logic goes in `main.py` (framework) or `main_with_no_framework.py`. Inherit from the template bot and override the forecasting methods.
- Python 3.11+ and Poetry for local runs. Has a dry-run mode.

### Rules that shape the design

- **No human in the loop.** No peeking and nudging, no rerunning a question because the result looks wrong, no manual submission. API only.
- **Private comment required on every forecast.** This is where the analytic write-up lives. Treat it as the product, not a formality.
- **One prize-eligible bot per person.** Extra experimental bots are allowed but must be labeled secondary (e.g. "v2" in the name).
- **Prize eligibility** requires sharing code or an architecture overview, a staff inspection, a demo on sample questions, and a methodology explanation. Build with this in mind: clean, explainable, documented.
- **Allowed:** updating the bot mid-season, testing on closed questions and past questions, training on public community predictions, teams.

### What winning bots do (Spring 2026 results)

- 173 bots competed (111 non-Metaculus). Metaculus Pro forecasters still beat the best bots, but the gap is closing each season.
- Top bots use frontier reasoning models. Using the strongest available model for the final prediction was the single most correlated feature with rank.
- Parallel research from several sources (AskNews, Perplexity deep research, search-enabled LLMs), then aggregation: median for binary, averaged distributions for numeric.
- Agent scaffolding beat plain prompting. Higher reasoning effort beat lower.
- The stock template ranked 18th. Custom research pipelines and model choice made the difference above that.

### Feedback loops, fastest to slowest

1. Compare against the community prediction (noisy but immediate).
2. Pastcasting on resolved historical questions (watch for leakage).
3. MiniBench round results every two weeks.
4. End-of-season results.

## Open items for XtremeSavageXD

- [x] Ethics check. Done 2026-09-11.
- [x] Payment check (Ramp). Done 2026-09-11.
- [x] Tournament name and IDs confirmed: Fall 2026 FutureEval Bot Tournament, project `33121` / `fall-futureeval-2026`.
- [x] Metaculus account and bot account created (XtremeSavageForecast).
- [x] Open source decided: yes, public repo from day one.
- [x] Credits form concern resolved 2026-09-11 (the key is the bot's, in GitHub secrets).
- [x] **Participation form** and LLM credit request (same form, https://forms.gle/aQdYMq9Pisrf1v7d8). Submitted by 2026-09-13.
- [x] OpenRouter account, key, and $25 prepaid (2026-09-13). Metaculus credit request pending.
- [x] AskNews API key in place (2026-09-13).
- [x] Second bot account `XtremeSavageForecast-v2` and its token in GitHub secrets (2026-09-13).
- [x] GitHub secrets in place (2026-09-13). Decision: **no `ANTHROPIC_API_KEY`**; XtremeSavageXD chose to rely on OpenRouter alone. An OpenRouter outage fails the question with `PROVIDER_FALLBACK` and it is retried next run.
- [x] First paid dry run done 2026-09-13: $0.38, clean. See `docs/HANDOFF.md` step 4.
- [x] Live on bot-testing-area 2026-09-13: main bot 3 questions, control bot 10. See `docs/HANDOFF.md` step 6.
- [x] Joined the Metaculus Discord, channel `build-a-forecasting-bot` (2026-09-13). XtremeSavageXD watches it; Claude has no access.
- [x] Data Needs Form (Bot Benchmarking access tier) submitted 2026-09-13. When granted, `cp_at_reveal` in `scores.py` starts filling in on its own.
- [x] GitHub Pages enabled 2026-09-13. Dashboard: https://xtremesavage.github.io/forecasting-bot/
- [ ] Remember the required end-of-season bot survey. No survey, no prize.

## Next step

Read `docs/HANDOFF.md`. It lists the exact order: accounts, secrets, first paid dry run, live on the testing area, then the Sep 21 warmup MiniBench.

## Sources

- Resources page: https://www.metaculus.com/notebooks/38928/futureeval-resources-page/
- FutureEval: https://www.metaculus.com/futureeval/
- Summer 2026 announcement: https://forum.effectivealtruism.org/posts/ZfLAN557rGWACKtmc/announcing-metaculus-summer-2026-futureeval-bot-tournament
- Spring 2026 announcement: https://www.lesswrong.com/posts/dvGYXZfiqCgcck9im/announcing-spring-2026-ai-forecasting-benchmark
- Spring 2026 results: https://www.lesswrong.com/posts/wZBbDqzfBjYG58CxK/futureeval-spring-results-pros-beat-bots-but-the-gap-is
- Template bot: https://github.com/Metaculus/metac-bot-template
- Framework: https://github.com/Metaculus/forecasting-tools
