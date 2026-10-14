# Contributing to BARKAV

Thanks for looking at BARKAV. It is a Persian, right-to-left desktop app for
construction-project finance, so a few rules matter more here than in a typical
project.

## Ground rules

1. **No real data, ever.** Do not commit databases, `secrets.local.json`,
   receipts, bank or cheque details, real names, phone numbers or Telegram chat
   ids. Use obviously fake values in tests (`09120000000`, `-1001234567890`).
2. **Money rules are not negotiable.** Read section 4 of
   [`app/AGENTS.md`](app/AGENTS.md) before touching anything that posts,
   deletes or counts money. In particular:
   - SQLite is the financial source of truth.
   - AI and Telegram *pending* data has no financial effect until a person
     approves it.
   - No financial row exists without a Data Entry record
     (`app/record_ownership187.py`). Do not weaken a test to get past this.
   - Decisions about an "open" or "cashed" cheque come from
     `app/cheque_status187.py` only.
3. **Persian UI stays Persian and right-to-left.** Keep Persian digits and the
   "۱ از ۲" form. Colours and fonts come from `app/barkav_ui/theme.py`, not from
   literals in a screen.
4. **Small, scoped changes.** The code is layered over earlier stages. Change
   the active `*_stage18_7.py` layer unless you can explain why a lower layer is
   needed.

## Setting up

```bat
git clone https://github.com/Pey1364/barkav-desktop.git
cd barkav-desktop\app
py -3 -m pip install -r requirements_18_7_1.txt -r requirements_dev.txt
```

## Running tests

Run from `app/`:

```bat
py -3 -m pytest tests\<file>.py -q -rf
```

- Tests must use a temporary database (`tmp_path`). Never point a test at a real
  project.
- Tests that open a Tk window need a desktop session. `tests/conftest.py` turns
  an unanswered message box into a failure; answer dialogs with `monkeypatch`.
- A new behaviour needs a test that fails without the change.
- Drive menus and clicks through the real event (for example `<Button-3>` for a
  context menu), not by calling the handler directly, and add a negative
  control.

## Pull requests

- One topic per pull request, with a short description of the user-visible
  effect.
- Say which tests you ran. If a test failed before your change too, say so.
- Do not reformat files you are not changing. Some of them are very large.
- If you used an AI coding agent, follow `AGENTS.md` the same way a human
  contributor would, and review the diff yourself before opening the PR.

## Reporting bugs

Open an issue with the steps, what you expected, what happened, and the
Windows and Python versions. Remove anything private from screenshots first.
For security problems, follow [SECURITY.md](SECURITY.md) instead.
