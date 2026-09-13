# Project: Forecasting Bot

This folder (`~/projects/forecasting-bot`) is the live copy as of 2026-09-12. The old OneDrive Desktop folder was deleted 2026-09-13.

Read `docs/HANDOFF.md` first: it says exactly where the build stands and what to do next. Then `README.md` for goals, rules, and open items. `docs/RESEARCH.md` holds the tournament research. The spec and plan are under `docs/superpowers/`..

Project status (2026-09-12): code complete on branch `build/v1`, 89 offline tests green, nothing run live. Autonomy level for this project is C: free rein on code and local files; confirm before spending money, sending messages, or the first submission to a live tournament.

Working rules for this repo:
- Run tests with `.venv/Scripts/python.exe -m pytest -q` (Python 3.12 venv; Actions use 3.11 via Poetry).
- Never edit `control_bot.py` or `bot_helpers.py`; they are the unmodified Metaculus template and the experiment's control.
- Model names, limits, and stage flags live in `config.yaml`, not in code.
- Every forecast writes a JSON record under `runs/`; the workflows commit those to `main`. The repo is public, so nothing secret may ever be logged.
- Change one thing at a time between MiniBench rounds and record why in `docs/HANDOFF.md`.
