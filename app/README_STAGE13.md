# Peymaan V2 — Stage 13

Final pre-data-entry polish release based on Stage 12.

## Changes
- Fixed adding an empty construction phase: a new phase is now visible immediately, even before any activity is added.
- Stronger white/blue zebra rows in dashboard metrics and compact tables.
- Dashboard adds total outstanding/un-cashed cheques.
- Quick bank reconciliation difference is green when positive and red when negative.
- Dashboard can export/print Excel, PDF and Print report.
- Telegram Desktop historical JSON import: old financial-looking group messages are imported as PENDING REVIEW only; no automatic financial effect.
- `/historypending` sends imported historical items to the admin private chat for normal approve/edit/reject handling.

## Historical Telegram messages
1. In Telegram Desktop export the relevant group/chat history as JSON.
2. Open Peymaan > Dashboard > `📥 تاریخچه تلگرام` and choose the JSON file.
3. The importer filters messages that look financial and creates review drafts with their original dates.
4. In the bot private chat run `/historypending` (optionally `/historypending 20`).
5. Approve/edit/reject each historical item normally.
6. Re-importing the same JSON is idempotent and does not create duplicates.

Historical imported messages use a synthetic local chat id; therefore they do not receive a Telegram reaction. This does not affect accounting or Sheets sync.
