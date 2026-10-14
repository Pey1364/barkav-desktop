# Peymaan V2 — Stage 7

Stage 7 adds the contractual revenue side without mixing it with real cash flow.

## Core rules

- A sale contract does **not** change petty cash.
- Only an approved buyer receipt creates a real `Transaction IN`.
- A buyer receipt is initially `UNMATCHED` and does **not** close an installment automatically.
- Installments are closed only after the admin explicitly confirms the suggested matching.
- Partial payment leaves the installment open and reminders continue for the remaining amount.
- Buyer reminders: 3 days before due date, on due date, then daily up to 7 days after due date until fully paid.
- User-facing dates are Jalali/Shamsi. Gregorian/ISO dates remain internal for scheduling and comparisons.
- SQLite remains the source of truth; Google Sheets is a mirror.

## New Telegram commands

- `/sales` — revenue dashboard and latest sales
- `/sale SALE-...` — one sale + installment details
- `/newsale` — start a private sale-contract form
- `/receive` — start a private buyer-receipt form
- `/unmatched` — receipts that have entered petty cash but are not yet matched to installments
- `/buyerreminders` — buyer reminder status
- `/reminders` — combined cheque + buyer reminder status
- `/remindercheck` — manually run both reminder engines

## Sale test form

```text
پروژه: بارکاو
بلوک: A
واحد: 12
طبقه: 3
متراژ: 120
پارکینگ: P12
انباری: S12
خریدار: نام خریدار
موبایل: 09...
شماره قرارداد: 1405-12
تاریخ قرارداد: 1405/05/20
مبلغ قرارداد: 10 میلیارد
اقساط:
1405/05/20 = 3 میلیارد
1405/06/20 = 3 میلیارد
1405/07/20 = 4 میلیارد
توضیحات: -
```

The installment sum must exactly equal the contract amount.

## Buyer receipt test form

```text
Sale ID: SALE-...
مبلغ: 3 میلیارد
تاریخ وصول: 1405/05/21
پرداخت‌کننده: نام خریدار
شرح: قسط اول
```

The bot first shows a confirmation preview. After confirmation, cash enters petty cash as `Transaction IN`, but installments remain unchanged until a second explicit **match confirmation**.

## Google Sheets tabs added

- `V2-واحدها`
- `V2-فروش‌ها`
- `V2-اقساط`
- `V2-وصول‌ها`

Existing Stage 4–6 tabs remain unchanged.

## Upgrade from Stage 6.1

1. Stop Stage 6.1 with `Ctrl+C`.
2. Extract Stage 7.
3. Copy your existing `secrets.local.json` and `data/` directory into Stage 7.
4. Run tests:

```bat
python -m unittest discover -s tests -v
python stage7_smoke_test.py
```

5. Run the bot:

```bat
python telegram_stage7.py
```

6. Optional: `/rebuildsheets` once if you want all new V2 revenue tabs created/rebuilt immediately.
