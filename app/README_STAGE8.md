# Peymaan V2 — Stage 8

Stage 8 adds the management GUI on top of the tested Stage 7 Telegram/SQLite/Google Sheets stack.

## Main additions

- Live management dashboard from SQLite (source of truth)
- Petty-cash balance, construction cost, open-cheque commitments, free cash after cheques
- Manager 10% account, withdrawals, creditor/debtor balance
- Manager historical chart and toman-day metrics
- Buyer sales, cash collections, receivables and overdue amounts
- Bank reconciliation history: system balance vs actual bank balance
- Financial-posting browser with safe GUI edit and soft delete
- GUI edits reuse the existing Stage 5 revision engine and keep linked IDs stable
- GUI deletes use soft-delete/void/cancel and preserve audit history
- Best-effort removal of the Telegram 👍 reaction after a GUI delete
- System-health tab (SQLite integrity, sync queue, duplicate Telegram-message check)
- `launcher_stage8.py` can launch both Telegram bot and GUI together

## Upgrade from Stage 7.1

1. Stop Stage 7.1 with `Ctrl+C`.
2. Extract Stage 8 to a new folder.
3. Copy these from your working Stage 7.1 folder into Stage 8:
   - `secrets.local.json`
   - `data\` (the whole folder containing `stage4_test.sqlite3`)
4. Do **not** replace the database with an older test database.

## Install / test

```bat
python -m pip install -r requirements_stage8.txt
python -m unittest discover -s tests -v
python stage8_smoke_test.py
```

Expected test result: `Ran 73 tests ... OK` and `STAGE 8 SMOKE TEST: OK`.

## Run

### Recommended: bot + GUI together

```bat
python launcher_stage8.py
```

Closing the GUI also stops the Telegram subprocess launched by the launcher.

### Or run separately

Terminal 1:

```bat
python telegram_stage8.py
```

Terminal 2:

```bat
python dashboard_stage8.py
```

Running them separately is useful when diagnosing Telegram/network issues.

## Bank reconciliation

On the Dashboard tab, enter the real bank balance in toman and a Shamsi date. The system stores:

- calculated system cash balance on that date
- actual bank balance
- difference = bank - system
- optional note

This does not modify the financial ledger. It only records a reconciliation checkpoint.

## Manager account

The Manager tab uses only approved, manager-fee-eligible construction expenses and actual `CONTRACTOR_FEE` withdrawals. It shows creditor/debtor days and positive/negative toman-days. Dates shown to the user are Shamsi.

## GUI edit/delete rules

- Editing uses the same posting revision logic as Telegram edits.
- Linked Expense / Transaction / Payment / Cheque IDs are retained where compatible.
- High-level type changes (e.g. Expense → Income) are blocked; delete the incorrect posting and enter a new one instead.
- Deletion is soft delete. Audit history remains in SQLite.
- A cashed cheque cannot be deleted by a simple GUI delete; it needs an explicit reversing financial entry.
- Google Sheets remains a mirror. GUI changes enter the normal sync queue and are sent while the Telegram bot/sync worker is running.

## Source of truth

SQLite remains the only authoritative ledger. Dashboard totals are recalculated from ledger rows; mutable cached balances are not stored.
