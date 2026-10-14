# Peymaan V2 — Stage 12

Stage 12 focuses on the executive dashboard, 30-day liquidity, compact reporting UX, and project identity fields while preserving the proven Stage 9.1 Telegram resilience layer.

## Dashboard
- Vertically stacked report sections with bold metric titles and info (ⓘ) help.
- Financial: construction cost, petty cash, free cash after open cheques, total inflow, **non-construction outflow total matching the خروجی‌ها sub-tab**, 30-day obligations, scheduled buyer receipts, and projected 30-day surplus/deficit.
- Cheques: total historical non-cancelled cheque value plus the next 30 days with issuer/account owner, bank, receiver, due date, and days remaining.
- Sales: contracts, receipts, receivables, upcoming 30-day buyer installments, and overdue buyer receivables.
- Loans: principal received, **sum of paid installments**, remaining debt, and a dedicated next-30-day installment table with bank, loan title, installment number, date, amount, and days remaining.
- Project profile on dashboard includes postal code, registration plate and municipal file number.
- Live Jalali date and 24-hour clock.

## Reporting
- More compact project-parameter and control rows.
- Budget phases can be added, renamed and deleted below the phase table; double-click opens activity detail where estimates are edited.
- Tooltips explain compact control buttons.
- Four separate per-square-metre KPIs:
  - construction cost / gross (non-saleable) m²
  - construction cost / saleable m²
  - total finished cost / gross m²
  - total finished cost / saleable m²
- Forecast profit/loss remains available; it is intended to be validated with real budget values after estimates are populated.

## Run
Double-click `Peymaan.bat`, or run:

```bat
python launcher_stage12.py
```

Copy your existing `secrets.local.json` and `data` folder from the working Stage 11 install before first real run.
