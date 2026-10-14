# Peymaan V2 — Stage 10

Stage 10 is the management-UI consolidation release built on the stable Stage 9.1 network layer.
SQLite remains the sole source of truth; Google Sheets remains a mirror.

## Main changes

- Professional colored management GUI, with all user-visible manager-fee labels changed to `حقوق مدیر پروژه`.
- All financial amounts are rendered with three-digit separators.
- Double-click / Enter / F2 editing is enabled on editable management tables; IDs and derived totals remain protected.
- Right-click table context menu, row copy, quick filtering, filtered totals, selected-row totals, Excel/PDF export and print.
- Global search remains separate from tabs and supports date/amount filters.
- Jalali calendar picker (`📅`) is used on GUI date inputs.
- Financial tabs order: All Transactions → Construction Costs → Inflows → Outflows → Loans.
- Manager account redesigned around one signed creditor/debtor view and `تومان‌ماه`; manager withdrawals are listed instead of a chart.
- Unit Master with stable IDs (`U-001`, `P-001`, `S-001`), floors, unit number, useful area, parking/storage and bulk creation.
- Reporting phase/activity master is editable. Main phase totals are derived; double-click a phase to edit activity estimates. Add / rename / delete phase buttons are below the table.
- Budget template is based on the supplied phase/activity workbook. Empty estimates are treated as zero.
- Cheques include issuer name and type (`فیزیکی` / `دیجیتال`), plus editable issue/due dates.
- Sales and bank reconciliations can be edited from their tables; reconciliation deletion is soft-delete with audit history.
- Project profile/document archive from Stage 9 remains available.
- `Peymaan.bat` launches Stage 10 by double click and intentionally keeps CMD visible for this stage.

## Start

1. Copy your working `secrets.local.json` and `data` folder from Stage 9.1 into this folder.
2. Install dependencies:

   `python -m pip install -r requirements_stage10.txt`

3. Run tests:

   `python -m unittest discover -s tests -v`

4. Optional smoke test:

   `python stage10_smoke_test.py`

5. Start by double-clicking `Peymaan.bat`, or run:

   `python launcher_stage10.py`

## Date entry

GUI date fields are Jalali and display a calendar when `📅` is clicked or the date field is double-clicked. Telegram text forms remain Jalali text because Telegram does not provide the desktop GUI calendar widget.

## Safety

Financial IDs, linkage IDs and computed totals are not directly editable. Changes that can affect ledger consistency are routed through the existing edit/revision services, audit log and sync queue.
