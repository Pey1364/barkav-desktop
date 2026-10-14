# AGENTS.md

Guidance for AI coding agents (Codex, Claude Code and others) working in this
repository. The full rule set is in [`app/AGENTS.md`](app/AGENTS.md); read its
section 4 (financial invariants) and section 6 (security) before any change.

## Where things are

- The application lives in `app/`. Run commands from there.
- Entry points: `BARKAV_19.1.1.bat` → `BARKAV_19.1.1.vbs` →
  `launcher_stage18_7.py` → `project_runner_stage18_7.py`.
- The active layer is the `*_stage18_7.py` files. `stage15` … `stage18_3`,
  `barkav/` and `barkav1871/` are dependencies; prefer fixing in the active
  layer.
- `dashboard_stage18_7.py` is very large and patches classes at import time near
  the end of the file (`Class.method = _function_187`). The last assignment is
  the one that runs, so search for the name with Grep before editing a method.
  Open large files with an offset and a limit.

## Rules that never bend

- SQLite is the source of truth. AI output and Telegram *pending* items have no
  financial effect until a person approves them.
- No financial row without a Data Entry record (`record_ownership187.py`,
  `FinanceDB.record_context`). Do not weaken a test to pass.
- "Open" and "cashed" cheque decisions come from `cheque_status187.py`.
- Keep execution, invoice, registration, payment, due and clearing dates apart.
- Never read, print or commit `secrets.local.json`, databases, `data/`, receipt
  files or anything that looks like real project data.

## Tests

- Run from `app/`: `python -m pytest tests/<file>.py -q -rf`.
- Tests use temporary databases only. Tk tests need a desktop session and open
  windows; do not run many at once.
- `tests/conftest.py` fails a test that waits on an unanswered dialog. Answer
  dialogs with `monkeypatch` on `messagebox`.
- For menus and clicks, send the real event (for example `<Button-3>`), and add
  a negative control.

## UI

- Persian, right-to-left. Keep Persian digits and "۱ از ۲".
- Take colours and fonts from `barkav_ui/theme.py` (`palette()`, `font()`).
- Multi-line text the user types (`tk.Text`) is built with
  `rtl_text187.install(widget)`.

## Before you finish

State what changed, which tests you ran and their result, and anything you did
not verify.
