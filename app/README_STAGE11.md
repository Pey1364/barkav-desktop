# Peymaan V2 — Stage 11

Stage 11 keeps the proven Stage 9.1/10 Telegram network-resilience layer and adds a more operational management dashboard plus Stage 10 UX fixes.

## Dashboard
- Live Jalali date and 24-hour clock.
- Info (ⓘ) help on dashboard KPIs.
- Financial section: construction cost, petty cash, free cash after open cheques, total inflow, total outflow.
- Next-30-day cheque section with issuer/account owner, bank, receiver, days to due, required liquidity and cash surplus/shortage.
- Sales/receivables section with total contracts, cash collected, total receivable, next-30-day receivables and overdue rows.
- Loan section with principal, net deposited proceeds, remaining debt and next-30-day installments.
- 30-day liquidity section showing obligations, expected buyer inflows, conservative cash position and projected cash position.

## Manager account
- Manager metrics populate even when there has never been a manager withdrawal.
- Withdrawal history is shown above the six signed metrics.
- Signed metrics: creditor/debtor days, average balance, Toman-month, project-manager fee, withdrawals and balance.
- Positive values are green and negative values are red.

## Reporting / phases
- Phase controls are directly below the phase table: add below selected row, rename, delete.
- Phase totals are read-only. Double-click a phase to open activity details and edit activity estimates.
- Activities can be added, renamed and safely deleted when unused.
- Reporting uses a vertical draggable splitter so more phase rows can be shown.
- Each SmartTable has independent row-height controls.

## Editing / keyboard / context menu
- Enter triggers the primary Save/Register action in data-entry dialogs (except multiline text and table activation).
- Double-click, Enter or F2 opens row editing in editable SmartTables.
- Right-click menus include edit and safe delete/cancel where supported.
- Financial deletion remains soft/void/cancel rather than destructive.

## Unit IDs
- Database `unit_id` stays immutable for referential integrity.
- User-facing unit/parking/storage IDs are editable (`display_unit_id`, `parking_display_id`, `storage_display_id`).
- This lets pre-sold units be renumbered without breaking linked sale contracts.

## Launch
Double-click `Peymaan.bat`. For Stage 11 the CMD window intentionally remains visible for diagnostics.

When upgrading from Stage 10, copy your existing `secrets.local.json` and the entire `data` folder into the Stage 11 folder before launch.
