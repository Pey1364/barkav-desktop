# Peymaan V2 — Stage 6 (Cheque lifecycle + Telegram reminders)

Stage 6 builds on the working Stage 5.3 ledger. SQLite remains the sole source of truth; Google Sheets remains an idempotent mirror.

## Upgrade from Stage 5.3

1. Stop Stage 5.3 with `Ctrl+C`.
2. Extract Stage 6 into a new folder.
3. Copy `secrets.local.json` from the working Stage 5.3 folder.
4. Copy the entire `data` folder from Stage 5.3 so the current SQLite ledger is preserved.
5. Keep `credentials.json` at the path configured by `GOOGLE_CREDENTIALS_FILE`.
6. Stage 6 upgrades the schema marker to version 5; no existing financial rows are deleted.

## Tests

```bat
python -m unittest discover -s tests -v
python stage6_smoke_test.py
```

Expected:

```text
Ran 53 tests
OK
STAGE 6 SMOKE TEST: OK
```

## Run

```bat
python telegram_stage6.py
```

## New commands

```text
/cheques       list open cheques with action buttons
/reminders     show/create reminder schedule
/remindercheck run one reminder delivery check immediately
```

Existing commands continue to work:

```text
/status
/sync
/rebuildsheets
/repairledger
/reactiontest
```

## Cheque lifecycle

### Issued cheque

Construction expense and manager fee are recognized on the expense realization date. The cheque is an outstanding commitment; petty cash is not reduced yet.

### `✅ پاس شد امروز`

- cheque -> `CASHED`
- creates exactly one `Transaction OUT`
- linked Payment -> `COMPLETED`
- expense payment status recalculates
- petty cash decreases only now
- construction cost and 10% manager fee are not duplicated
- future reminders are cancelled
- SQLite changes are queued to the existing V2 Sheets tabs

### `↩️ برگشت خورد`

- cheque -> `RETURNED`
- no cash Transaction is created
- construction expense and manager fee remain realized
- returned cheque remains an outstanding commitment
- pre-due reminder slots are cancelled because the due event has already been explicitly handled

A returned cheque can later be marked cashed if it is successfully presented again.

### `🚫 لغو چک`

- only allowed for an uncashed cheque
- cheque -> `CANCELLED`
- linked cheque Payment -> `CANCELLED`
- underlying construction Expense is NOT cancelled
- cash is unchanged
- manager fee is unchanged because the realized construction expense still exists
- vendor/expense becomes unpaid or partially paid according to other payments

A cashed cheque cannot be directly cancelled; it requires an explicit correction/reversal in a later stage.

## Reminder engine

Stage 6 creates Telegram-private reminder slots from `N` days before due date through due day. The schedule is idempotent across restarts.

Default configuration is intentionally editable:

```json
"STAGE6_CHEQUE_REMINDERS_ENABLED": true,
"STAGE6_CHEQUE_REMINDER_DAYS_BEFORE": 5,
"STAGE6_CHEQUE_REMINDER_TIMES": "09:00,14:00,19:00",
"STAGE6_REMINDER_CHECK_SECONDS": 60
```

The times are defaults, not accounting rules. Change them in `secrets.local.json` without modifying code.

Old missed reminder slots are expired instead of being sent in a flood after a long restart. Network failures are logged and the current slot remains retryable.

## Stage 6 accounting invariants

For a 300M construction expense paid by a future cheque:

Before cheque clears:

```text
construction cost = 300M
manager fee = 30M
cash effect = 0
open cheque commitment = 300M
```

After cheque clears:

```text
construction cost = 300M
manager fee = 30M
cash effect = -300M
open cheque commitment = 0
```

No duplicate expense or manager fee is created on clearing.


## Stage 6.1 fix
- Local fallback now extracts Jalali cheque due dates from text.
- Cheque edit prompts explicitly show `سررسید چک`.
- Edit parser accepts multiple due-date aliases.
