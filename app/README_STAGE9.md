# Peymaan V2 — Stage 9 Management, Budget & Project Archive

Stage 9 turns the Stage 8 test dashboard into the management workspace while keeping SQLite as the single source of truth and Google Sheets as a mirror.

## Main GUI structure

- داشبورد
- حساب مدیر
- ثبت‌های مالی
  - کلیه تراکنش‌ها
  - هزینه ساخت
  - ورودی‌ها
  - خروجی‌ها
  - وام‌ها
- چک‌ها
- فروش و مطالبات
- تاریخچه تطبیق بانک
- گزارش‌گیری
- سلامت سیستم

A global search button is placed in the top navigation instead of a separate search tab. Every data table has quick filtering, row count, filtered amount total, copy, Excel export, PDF export and printing.

## Visible terminology

All Stage 9 management screens use **حقوق مدیر پروژه**. The ledger field remains technically compatible with old records/phrases such as «حقوق پیمان» so older data is not broken.

## Project profile & document archive

The top bar contains **مشخصات پروژه**. It stores:

- project name
- address
- postal code
- description
- scanned deed/title document
- permit/license
- completion certificate
- other PDF/JPG/PNG project documents

Documents are copied into the local Stage 9 data archive and can later be opened or printed from the GUI.

## Construction phase master & budget

`phase_budget_template.xlsx` is the Stage 9 budget template based on the supplied phase/activity workbook.

- 30 construction phases
- 297 phase/activity master rows
- each activity has an estimate field
- blank estimate = zero
- imports are versioned in SQLite
- importing a new budget version never deletes actual expenses
- expenses are linked by stable phase/activity IDs

The Construction Expense tab allows assigning **مرحله ساخت** and **نوع هزینه/فعالیت** to actual expenses. This is the base for future cost + schedule control.

## Reporting / forecast

Manual report inputs include:

- gross/non-useful construction area
- saleable/useful area
- unit count and unit areas
- monthly inflation
- months remaining
- current presale price per m²
- projected end-sale price per m² (automatic, manually overridable)
- miscellaneous unbudgeted cost
- target profit percentage

The report engine calculates:

- initial budget vs current forecast
- actual-vs-budget performance factor
- inflation-adjusted forecast to completion
- forecast construction cost including project-manager fee
- land + construction total finished cost
- construction and finished cost per gross/saleable m²
- projected sales revenue, profit/loss and profit percentage
- required average sale price for remaining units to reach target profit
- financing gap and estimated saleable area that must be presold to fund the project
- phase-level and activity-level budget / actual / forecast / variance tables

## Loans

Stage 9 adds a dedicated loan ledger and Google Sheets mirrors:

- `V2-وام‌ها`
- `V2-اقساط وام`

Loan fields include lender/bank, loan type, principal, actual cash received, received Shamsi date, interest rate, total interest, bank fees, total repayment, installment count/amount, first due date, guarantors, collateral and contract number.

Receiving a loan creates exactly one real `IN` transaction for the **actual amount received**. Loan principal/interest metadata does not double-count cash.

Loan installment payment creates a non-construction `OUT` transaction and does not create construction cost or project-manager fee.

Telegram Stage 9 also recognizes loan receipt/payment messages:

- loan receipt in the group -> private loan-detail form -> confirmation -> loan + cash IN + 👍
- loan installment payment in the group -> loan/next-installment match -> private confirmation -> cash OUT + installment update + 👍
- commands: `/loan`, `/loans`, `/loandraft`, `/loanreminders`
- loan installment reminders: 3 days before, due date, and up to 7 days after while unpaid

## Receipts and attachments

Financial records can have local JPG/PNG/PDF receipts attached. The GUI displays a receipt count and opens archived files on demand. Project documents use a separate project-document archive.

## Upgrade from Stage 8

1. Stop Stage 8 with `Ctrl+C`.
2. Extract Stage 9 into a new folder.
3. Copy **only** these from the currently working Stage 8 folder:
   - `secrets.local.json`
   - the whole `data\` folder
4. Do not replace the current database with an older repaired/test database.

## Install / test

```bat
python -m pip install -r requirements_stage9.txt
python -m unittest discover -s tests -v
python stage9_smoke_test.py
```

Expected automated result for this build: **80 tests OK** and `STAGE 9 SMOKE TEST: OK`.

## Run

Recommended:

```bat
python launcher_stage9.py
```

Or separately:

```bat
python telegram_stage9.py
```

and in another CMD:

```bat
python dashboard_stage9.py
```

## First Stage 9 checks

1. Open **مشخصات پروژه**, save name/address/postal code and add a sample JPG/PDF document; open and print-test it.
2. Open **ثبت‌های مالی > هزینه ساخت**, assign a phase/activity to one test expense.
3. Open **گزارش‌گیری**, import `phase_budget_template.xlsx`, set project parameters, and verify the forecast cards and phase table.
4. Create one small test loan from the GUI or `/loan`; confirm only the actual received amount enters cash.
5. Test one installment payment and confirm it appears as a non-construction OUT transaction.

All user-visible dates remain Shamsi. Gregorian/ISO dates are internal only.
