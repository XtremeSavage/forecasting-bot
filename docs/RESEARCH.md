# Research: Past Winners, Rules, and Fall 2026 Facts

Compiled 2026-09-11 from Metaculus notebooks, LessWrong/EA Forum writeups, the two open-source top bots, and the live Metaculus site (via Chrome). Sources at the bottom.

## 1. Fall 2026 confirmed facts

| Item | Value |
|---|---|
| Tournament name | Fall 2026 FutureEval Bot Tournament |
| Project ID / slug | `33121` / `fall-futureeval-2026` |
| Prize pool | $50,000; 300-400 questions |
| First questions open | **September 28, 2026**. Slow for first 1-2 weeks, then picks up |
| Questions stop opening | A few weeks before January 1, 2027 |
| Warmup MiniBench | Starts **September 21, 2026 00:00 UTC**. Most MiniBench questions launch in the first few days; second week is usually empty |
| Testing area | `bot-testing-area` / `32977`. One question of each type. Unscored |
| Question types used | Binary, Numeric, Discrete, Multiple Choice only |
| Late join | Allowed anytime; start mid-leaderboard at 0 |
| Summer 2026 | Done. Resolves by Sep 15, cutoff Sep 30. Slug `summer-futureeval-2026` / `33022` |
| Fall 2025 | Slug `fall-aib-2025` / `32813`, 377 questions |
| MiniBench | ID `minibench`. $1k every two weeks, ~60 questions, AI-generated and AI-resolved, noisier |
| Market Pulse | $7k, bots eligible, requires numeric group questions and continuous updating. Not our focus |

### New policies for Fall 2026

- **Required participation form** (3 required questions). Also doubles as the LLM credit application. Must fill out.
- **Credits are selective this season.** They ran out of money in Summer. Some applicants get nothing. Experiment: ~$100 initial, auto top-up if MiniBench performance is above average. Open-source bots get roughly double.
- **Commercial bots are not prize-eligible.** Hobbyist and open-source bots benefit. We qualify as hobbyist.
- **Required end-of-season bot survey** for prize eligibility. Skipping it can get you disqualified.
- **Old private comments get archived** after 30 days if over 1,000 chars. Full text via `api/comments/[id]/` (8 calls per 10 sec). Matters if we read our own past comments for backtesting.
- **Google credits** share a 150 req/min rate limit across all participants. Expect 429s if we lean on Gemini.
- forecasting-tools is at v0.3.0. Agent features now need the `[agents]` extra.
- AskNews accounts must be renewed each season (Discord @freqai or contact@asknews.app with bot name, email, name, LinkedIn, affiliation).

### Rules (unchanged)

- No human in the loop. No previewing and rerunning. No manual submission. API only.
- Comment required on every forecast, must accurately reflect the bot's reasoning. Private comments preferred.
- One prize-eligible bot per person. Extra bots must be labeled v2, v3, etc.
- Prize winners: share code or an architecture description, staff inspection, demo, methodology writeup.
- Allowed: updating the bot mid-season, testing on closed/past questions, teams (prize split evenly).
- Forbidden: creating external markets to help the bot, testing on open tournament questions then updating.
- Payment via Ramp bank transfer. Timeline after resolution: surveys 0-2 wks, completion 0-4 wks, processing 0-2 wks.

## 2. Scoring (what actually decides rank)

- Base unit is the **log score**: ln(p) for the outcome that happened. Continuous questions use ln(pdf at outcome), with a uniform 0.01 floor added to every pdf so a miss can't go to minus infinity.
- **Peer score** = 100 x (your log score minus the average of everyone else's log scores) on that question. Sums to zero across all forecasters per question.
- **Spot peer score** = peer score evaluated at one instant (when the community prediction is revealed). Only the forecast standing at that moment counts. No time-averaging, no coverage. So the bot must have a forecast in place before the reveal, and later updates don't matter.
- **Tournament rank** = sum of peer scores across all questions (0 for any question you skipped). **Prize share** is proportional to that sum **squared**. Negative total means no prize.
- Practical consequences:
  - Skipping a question costs you the peer score you would have earned. Forecast everything.
  - Extreme wrong answers are brutal. 99% wrong is -4.6 log score vs -0.01 when right. Binary is clamped to [0.1%, 99.9%].
  - Peer score is relative to *the other bots*, not to truth. Beating the pack by a little on many questions beats hero calls.
  - Best possible binary peer score per question is +691 and worst is -691. Continuous is +/-408.
  - Fall 2025 winner totaled ~6,969 over 377 questions, so roughly +18.5 per question on average. Spring 2026 top-10 averaged 13-19 per question. That is the target band.

## 3. Season-by-season winners

### Q3 2024
- Pros beat bots decisively (p = 0.036). A single-shot GPT-4o prompt beat many multi-agent chain-of-prompt bots.
- Bots were positively biased: "when bots forecast 29%, it happens 12% of the time." Poor discrimination (21-point yes/no separation vs 36 for pros). Scope insensitivity: P(B)+P(C) = 1.24 x P(A) on nested questions.

### Q4 2024
- Winner **pgodzinai** (Phil Godzin), peer avg 13.2. Approach: group related questions for internal consistency; Perplexity + AskNews; 3 runs of GPT-4o + 5 of Claude 3.5 Sonnet, drop extremes, average; prompt encodes "you are historically overconfident" and "~35% of questions resolve Yes." Invested 15-40 hours total.
- Pros still better, mainly via **discrimination, not calibration**. Both were well calibrated.
- 76% of winners used repeated LLM calls with median/mean. Only one used fine-tuning.
- One bot solo beat every multi-bot aggregate, meaning the top bot pulled well ahead.

### Q1 2025
- Winners **manticAI** ($7,685), **acm_bot** ($5,499), **GreeneiBot2** ($4,065). manticAI: news, Wikipedia, econ/finance data, external forecasts, "basic forecasting techniques," incremental improvement.
- Template bot metac-o1 top among Metaculus bots and 25th of 617 in the human Quarterly Cup.
- Base model is the biggest factor. But twsummerbot placed 8th on plain gpt-4o via better prompting and tool use, so scaffolding matters when done well.
- Bots were bad at multiple choice (-37.5 avg) vs binary (-9.8) and numeric (-8.7).
- 10 of 11 winners aggregated multiple forecasts. AskNews beat Exa and Perplexity (not significant).

### Q2 2025
- Winners **Panshul42** ($7,550, open source), **pgodzinai** ($4,563), **CumulativeBot** ($3,270). Template o3+AskNews placed 2nd overall.
- Panshul42 pipeline: question analysis, LLM-generated search queries, async retrieval (Google Search/News, AskNews, Perplexity, BrightData scraping), context synthesis, then a 5-agent committee (2x Claude 3.7 Sonnet, 2x o4-mini, 1x o3 double-weighted) with some agents prompted for outside view and some for inside view, weighted average. Numeric: 201-point CDF from predicted percentiles.
- Pros beat bots by -20.03 head-to-head (significant).

### Fall 2025
- Winners **Preseen-Atlas** (6,969 pts, $6,859), **manticAI** (6,523, $6,009), **GreeneiBot2** (6,404, $5,793), **mmBot** (5,035, $3,581). Bot community prediction would have placed 4th. 377 questions.
- Survey (39 respondents): frontier models are universal now. **Research breadth was the strongest predictor of winning** (r = 0.42, p ~ 0.006). Winners used 1.75 distinct research sources on average vs 1.00 for non-winners. Typical winning stacks: AskNews + Perplexity + custom scrapers, or AskNews + Exa + OpenAI web search.
- Scaffolding gap now equals model gap: within the same model family, top scaffolds beat baseline by 5-11 points per question and bottom ones lost 6-16. A ~27-point spread from scaffolding alone.

### Spring 2026
- Top 10: **GreeneiBot2**, Preseen-Atlas, SynapseSeer, manticAI, Preseen-Chestnut, cassi, pgodzinai, CumulativeBot, mmBot, jonahSingerbot. **nostreambot** 11th (top open source). Template GPT-5.1-high+AskNews 18th of 173.
- Pros beat bots by only 1.25 points (p = 0.247, not significant). Nine of ten individual pros beat every individual bot.
- GPT-5.x usage correlated with rank (GPT-5.4 r = 0.42). Opus correlation ~0. Nothing reached significance after correcting for 33 tests.
- Swapping search providers made no measurable difference.
- Aggregating ~10 diverse bots performed best; beyond 10 it declined. Top-10 CIs overlapped heavily, so rank among the top is partly noise.
- Question mix: 56% binary (67% resolved No), 31% numeric, 13% MC.
- 7 of top 10 bot makers were hobbyists, including 2 of the top 3.
- Agentic bots gained ground on single-prompt baselines.

### Summer 2026 (in progress)
- 326 questions, ~180 bots forecasting each. Questions are short-fuse: many resolve within 1-2 weeks of opening ("as of September 10, 2026", "before September 7, 2026"). Topics span geopolitics, econ data releases, weather, box office, legislation, humanitarian funding. Expect the same style in Fall.

### Recurring names
GreeneiBot2, manticAI, Preseen-Atlas, pgodzinai, mmBot, CumulativeBot appear in the top ranks across multiple seasons. Consistency over four seasons means their approach is robust, not lucky.

## 4. What the top bots actually do

**GreeneiBot2** (1st Spring 2026, 3rd Fall 2025, 3rd Q1 2025; not open source, overview public): async Python, pulls open questions, runs several research processes in parallel (AskNews, Perplexity sonar-reasoning-pro and sonar-deep-research, GPT-5 search via OpenRouter, link assistants that screenshot resolution-source pages). Multiple forecasting calls via litellm across OpenRouter/OpenAI, multi-run aggregation, structured CDFs for numeric, forecast validation against platform rules.

**nostreambot** (11th Spring, 9th Fall 2025, MIT-licensed, Metaculus recommends it as the "advanced starting point"): seven stages.
1. Research fan-out: AskNews (primary, summarized into an analyst briefing), OpenAI native search, Gemini grounded search, yfinance/FRED, prediction-market snapshots (Polymarket, Kalshi, Manifold, PredictIt), resolution-source URL fetcher. Each soft-fails independently.
2. Gap-fill: an analyzer LLM lists missing facts, parallel searches fill them; plus a bounded agentic search loop. Skipped when close time is near.
3. Forecaster fan-out: 3 frontier models (latest OpenAI, Anthropic, Google; Grok added as a low-correlation member) each produce structured JSON reasoning + forecast. Numeric: percentiles to PCHIP CDF on a 201-point grid.
4. Min-forecasters guard, then **median** aggregation (stacking exists but is disabled in prod).
5. Comment assembly with per-model rationales and the full research bundle, trimmed to 65k chars.
6. Publish gate: re-check the question is still open before POSTing. No retry on 4xx.

Their retrospective: worst misses came when all three models agreed on a shared bad briefing. A pipeline bug once published 0.20 when the models said ~80% (-35 peer score). A dry API key led to a lone-model publish scoring -105. Lone extreme calls were right 4 of 9 times; extremes shared by all models were right 21 of 23. Lesson: most catastrophic losses are plumbing, not judgment.

**Panshul42** (1st Q2 2025, open source): see above. Two things to steal: explicit outside-view vs inside-view agents, and generating search queries with an LLM before retrieval.

**pgodzinai** (1st Q4 2024, 7th Spring 2026): question grouping for consistency, base-rate reminders in prompt, trim extremes then average.

**Metaculus template** (18th of 173 Spring 2026 with GPT-5.1-high + AskNews): one AskNews search, a ~30-line prompt, 5 forecasts, aggregated. This is our floor.

## 5. Advice from bot makers (Spring 2026 survey, near-verbatim)

What worked:
- "Forecasts are only as good as your ability to find/parse/synthesize info."
- "Stripping LLM-as-researcher in favor of raw retrieval was the biggest win."
- Cheap diverse ensembles beat one expensive model. Separate models for research vs forecasting vs parsing.
- "Aggregate in logit space, not probability space."
- "Anchor on an explicit empirical base rate before the model sees news."
- Cap predictions to prevent overconfident nonsense.
- Track Brier and log score inside the bot. "Change one thing at a time and measure it." Run variants in parallel to separate signal from noise.
- "A cost guard that rejects any model above a per-call ceiling is not optional."

What didn't:
- "More diversity does not equal more performance." One maker had 13 named LLM roles and collapsed to 2 models.
- Monte Carlo approaches were "atrocious for calibration."
- Post-hoc extremization and temperature scaling "distorted the original prediction in ways that seemed more damaging than helpful." Multiple makers said extremization hurt.
- Newer models don't automatically forecast better; Claude Opus 4.6 was noted as overconfident. "The system prompt alone can turn a great LLM into a terrible one."
- Code execution in autonomous pipelines is "exceptionally error-prone and high-risk."

Biggest single losses:
- "Lost 90 peer score" by not telling the model Metaculus's convention: assume the event has NOT already happened unless research shows it has.
- "Before X date" questions are forward-looking; one bot's worst miss was misreading that.
- Parser failures cascading into bad publishes.
- Two-thirds of one bot's spend went to questions that never got scored (closed or annulled). Measure cost per *scored* question.
- Backtests are contaminated: "retrieval leaks the answer."

What they'd do differently: invest in resolution-criteria edge cases up front; prioritize research quality over prompt tuning; "teach general forecasting judgment rather than specifying every situation"; test on resolved questions of every type before going live.

## 6. What competitors plan for Fall 2026 (from the public bot-plans page)

Important correction to our README: analytic-tradecraft ideas are **not** absent this season. Several Fall 2026 plans borrow directly from the intel world:
- **lakshya-bot**: hindsight explanation generation, explicitly inspired by *Psychology of Intelligence Analysis* (Heuer). Focus on MC.
- **Beskar-Bot**: multi-agent council with sub-researchers, adversarial reviewer, source-credibility grading, "inspired by CIA Red Cell protocol."
- **MASXAI-BOT**: "Council of Doctrines" (IR theory, conflict dynamics, economic statecraft) with a router and log-odds aggregation.
- **dtfr-bot**: OSINT centaur demo with a 13,500-document Chinese-language corpus, decompose, base rates, weigh evidence for/against.
- **Killian**: "resolution forensics" as a first-class stage (adversarial parsing of criteria, URL verification, alternative interpretations), 8 independent scratchpad forecasts across 3 model families, disagreement-triggered crux research.
- **Oraky**: BLIND track (no market/crowd data) vs RESEARCH track, stores both, measures the delta. Anti-look-ahead enforced in code.
- **signal2noise**: 13 reference-class base-rate modules from structured databases, 40+ live data sources, logit-weighted blend of base-rate anchor, current signals, and resolution-criteria adjustment. Open source.
- **pancratic-bot**: three lenses (outside view, inside view, status-quo/inertia), log-odds median with agreement-scaled extremization. Thesis: "most bots lose points to overconfidence and poor calibration, not lack of knowledge."
- **germanr-bot**: six reasoning members (reference-class, mechanistic, status-quo, market-aware, domain specialist, tail-risk), winsorized geometric mean.
- **Cassandra-bot**: six-model ensemble with outside/inside/devil's-advocate, horizon-scaled extremization.

So the opportunity is not "nobody has thought of tradecraft." It is that nobody has *finished and measured* it, and most of these are single-technique bolt-ons. The differentiator has to be a coherent, disciplined pipeline that is actually tested against resolved questions, not a list of intel buzzwords in a prompt.

## 7. Implications for our design

Hard constraints from the evidence:
1. **Plumbing first.** The biggest losses in every retrospective are bugs: wrong number published, one-model publishes on a dead key, parser failures, missed questions. Guards, validation, and a publish gate are worth more than any prompt.
2. **Forecast every question, before the reveal.** Spot scoring plus squared-sum prizes punish gaps.
3. **Frontier model for the final call.** The GPT-5.x family has the best track record. Use the strongest model we can afford for the forecast step; cheaper models for parsing and research summarization.
4. **Two or more research sources.** AskNews plus at least one of Perplexity, Exa, or native web search. Fetch the resolution source directly when there is a URL.
5. **Ensemble and take the median** (in logit space). 3-5 members, diverse model families. Don't go past ~10.
6. **No post-hoc extremization.** Calibration comes from base-rate anchoring and evidence discipline, not from a multiplier.
7. **Explicit "has this already happened?" and "before X date" handling** in the prompt. Cheap, and it prevented 90-point losses for others.
8. **Multiple choice needs special care**: bots historically lose the most there.
9. **Numeric**: percentiles to a smooth 201-point CDF, respect open/closed bounds, don't starve tails.
10. **Log everything** per forecast (research, each member's reasoning, aggregate, cost) so we can do our own residual analysis after MiniBench rounds.
11. **Cost guard** per call and per question. Track cost per scored question.
12. The private comment should be the structured analytic product: key assumptions, base rate, evidence for/against with source reliability, ACH-style alternative outcomes, confidence statement, final number. That is both the tradecraft hypothesis and the prize-eligibility documentation.

Where tradecraft plausibly adds measurable value, given the failure modes above:
- **Resolution-criteria forensics** (what exactly resolves this, what's the trap) maps to the "key assumptions check."
- **Source reliability weighting** maps to the retrieval-quality bottleneck.
- **Base rate before evidence** is the outside view; several top bots do it, few do it rigorously.
- **ACH**: enumerate outcomes, score evidence against each, resist the story that fits. Directly targets the positive-bias and overconfidence findings.
- **Status-quo bias as a feature**: 67% of binaries resolve No. "What has to change for Yes?" is the right framing.

## 8. Open questions for XtremeSavageXD (batched)

1. Credits form: what is the safety concern? If it's OpenRouter key/billing safety, mitigations exist (per-key spend limits, zero-data-retention default, separate key per bot). If it's about the form's data request, say what it asks for and we can decide. Without credits we pay ~$1-1.50 per question x 300-400 questions, roughly $400-600 for the season plus MiniBench.
2. Open source or not? Open-source bots get roughly double credits and Metaculus actively promotes them. It also fits the "public credential" goal. Downside: competitors can copy the tradecraft layer.
3. Model access: do you have your own OpenAI or Anthropic API keys, or is OpenRouter (via credits or self-funded) the plan?
4. AskNews: registered yet? It's free and the single most-used source among winners.

## Sources

- Fall 2026 announcement: https://www.metaculus.com/notebooks/45615/announcement-of-futureeval-fall-2026/
- Resources page: https://www.metaculus.com/notebooks/38928/futureeval-resources-page/
- Spring 2026 analysis: https://www.metaculus.com/notebooks/45373/spring-2026-futureeval-analysis/
- Spring 2026 bot-maker advice: https://www.metaculus.com/notebooks/45336/bot-maker-advice-spring-2026/
- Spring 2026 results (LessWrong): https://www.lesswrong.com/posts/wZBbDqzfBjYG58CxK/futureeval-spring-results-pros-beat-bots-but-the-gap-is
- Bot plans catalog: https://www.metaculus.com/notebooks/43497/bot-plans/
- Fall 2025 survey: https://www.metaculus.com/notebooks/43337/fall-2025-futureeval-survey/
- Fall 2025 tournament: https://www.metaculus.com/tournament/fall-aib-2025/
- Q2 2025 results: https://www.metaculus.com/notebooks/40456/q2-ai-benchmark-results/ and winners https://www.metaculus.com/notebooks/39140/winners-of-q2-2025-ai-benchmark-tournament/
- Q1 2025 results: https://www.metaculus.com/notebooks/38673/q1-ai-benchmarking-results/ and winners https://www.metaculus.com/notebooks/37692/winners-of-the-q1-2025-ai-forecasting-benchmark-tournament/
- Q4 2024 results: https://www.metaculus.com/notebooks/35291/q4-ai-benchmarking-results/
- Q3 2024 results: https://www.metaculus.com/notebooks/28784/aibq3results/
- Scores FAQ: https://www.metaculus.com/help/scores-faq/
- Panshul42 bot: https://github.com/Panshul42/Forecasting_Bot_Q2
- nostreambot: https://github.com/No-Stream/metaculus-bot (docs/architecture.md, docs/performance_analysis.md)
- Template: https://github.com/Metaculus/metac-bot-template
- Summer 2026 announcement: https://forum.effectivealtruism.org/posts/ZfLAN557rGWACKtmc/announcing-metaculus-summer-2026-futureeval-bot-tournament
