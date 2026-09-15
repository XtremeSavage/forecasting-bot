# Project: Forecasting Bot

This folder (`~/projects/forecasting-bot`) is the only copy.

Read `docs/HANDOFF.md` first: it says exactly where the build stands and what to do next. Then `README.md` for goals, rules, and open items. `docs/RESEARCH.md` holds the tournament research. The spec and plan are under `docs/superpowers/`. XtremeSavageXD's working preferences live outside the repo in `~/.claude/CLAUDE.md`.

Current status lives at the top of `docs/HANDOFF.md`; do not duplicate it here. Autonomy level for this project is C: free rein on code and local files; confirm before spending money, sending messages, or the first submission to a live tournament. XtremeSavageXD pays for OpenRouter out of pocket while the Metaculus credit request is pending, so mention the cost of any paid run before starting it.

Working rules for this repo:
- Run tests with `.venv/Scripts/python.exe -m pytest -q` (Python 3.12 venv; Actions use 3.11 via Poetry).
- Paid runs: `run.py --mode dry --limit 1` (no publish, ~$0.40) and `run.py --mode test --limit N` (publishes to bot-testing-area). Both need `.env`. After a local live run, commit `runs/` and push, or the scheduled workflows will re-forecast those questions.
- Never edit `control_bot.py` or `bot_helpers.py`; they are the unmodified Metaculus template and the experiment's control.
- Model names, limits, and stage flags live in `config.yaml`, not in code.
- Every forecast writes a JSON record under `runs/`; the workflows commit those to `main`. The repo is public, so nothing secret may ever be logged.
- Change one thing at a time between MiniBench rounds and record why in `docs/HANDOFF.md`.

Gotchas:
- A Metaculus post can be a question group with several subquestions sharing one `post_id`. Identity is always `question_id`; the record filename is `{post_id}_{question_id}_{HHMMSS}.json`.
- The forecasting-tools `NumericDistribution` applies Metaculus's 1% uniform floor when it standardizes a CDF. Apply it exactly once, at publish. `aggregate_numeric` works on raw CDFs (`standardize=False`) for this reason.
- Bot accounts cannot see community predictions or resolutions on questions they never forecast; `cp_at_reveal` is None until the Bot Benchmarking data tier is granted.
- In `.env`, leave unused keys blank (`NAME=`), never `REPLACE_ME`; a placeholder counts as a value and the AskNews client will try to use it.
- `ANTHROPIC_API_KEY` is intentionally blank (XtremeSavageXD's call); the fallback path fails fast and records `PROVIDER_FALLBACK`.
- The `!` prompt runs Git Bash, not PowerShell. Long inline Python heredocs in the Bash tool can fail to parse; write the script to the scratchpad and run it.
- Line endings: files are LF in the repo and Git warns about CRLF on every commit on Windows. Ignore the warnings.
