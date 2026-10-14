# Peymaan V2 — Stage 15

Stage 15 focuses on two critical areas before bulk entry of real project expenses:

1. Receipt / invoice intelligence and historical Telegram media import.
2. A pre-launch Project Center for selecting or creating an isolated active project.

## Receipt pipeline fixes

- Telegram photos and image documents are downloaded, archived, and attached to the Pending record before financial posting.
- The original archived image is sent to Vision AI; OCR uses a separately preprocessed copy.
- OCR text is explicitly included as supporting evidence in the AI prompt.
- Historical Telegram Desktop imports no longer discard photo/file messages just because the local text parser cannot find an amount or transaction type.
- Missing historical media is reported explicitly instead of being silently skipped.
- The Approval Center can re-run AI analysis for one image or all imported images.
- If Vision fails, the item remains `NEEDS_REVIEW`; local text/OCR fallback is never presented as successful Vision analysis.
- Optional provider chain: Gemini first, then OpenAI if an API key is configured, then manual/OCR review.
- Duplicate protection for re-imported Telegram history is retained.

## Approval Center UX

- Receipt image can be opened from its archived path.
- Source/provider/Vision status are displayed.
- Tooltips are clamped to the usable Windows work area and move above controls near the taskbar.
- GUI and Telegram approvals continue to operate on the same Pending record.

## Project Center (Stage 15 pilot)

`Peymaan.bat` now opens a Project Center before the main dashboard.

- Existing current data is registered as the first project (`PRJ-001`) without moving or rewriting its ledger.
- New projects get an isolated SQLite database under `data/projects/<project_id>/`.
- A wizard collects project information, Telegram Group ID, verifies bot access, binds the group, and configures the spreadsheet name.
- One Group ID cannot be bound to two projects.
- The selected project is applied to the environment before the dashboard and bot are loaded.

### Important limitation

Stage 15 is an **active-project multi-project pilot**: the selected project is isolated and active for the current application session. A single continuously running bot that concurrently routes updates, reminders, Sheets sync, and approvals for multiple project groups at the same time is **not yet implemented**.

## Installing over Stage 14

1. Stop Stage 14.
2. Extract Stage 15 into a new folder.
3. Copy only your current `secrets.local.json` and `data` directory from Stage 14 into Stage 15.
4. Install requirements:

   `python -m pip install -r requirements_stage15.txt`

5. Double-click `Peymaan.bat` or run:

   `python launcher_stage15.py`

The Project Center should open before the dashboard.

## First live receipt test

Send one known `#تست` receipt photo to the active project's Telegram group.

In Approval Center verify:
- content type is PHOTO (or IMAGE_DOCUMENT), not TEXT;
- the archived image opens;
- Vision status/provider is visible;
- amount/date/payer/payee/description are populated or explicitly marked as needing review;
- no financial effect occurs until approval.

Do not bulk-approve imported history yet. Test 5–10 varied receipts first.

## Historical Telegram import

For best results, export the group from Telegram Desktop as JSON **with photos/files included** and preserve the exported folder structure. Select the JSON from the dashboard's Telegram-history importer.

The importer reports media candidates, text candidates, missing media, duplicates, and pending records. Imported media can then be analyzed by Vision AI from Approval Center.

## Optional OpenAI fallback

If configured, `OPENAI_API_KEY` enables an optional second Vision provider after Gemini. This is separate from a ChatGPT subscription and is not required for the application to run.

## Budget workbook link patch (current working build)

This build also understands the current Peymaan 32-phase workbook (`phase_budget_current.xlsx`).

- The `روکش` sheet defines the 32 phase order/names.
- Each `NN-...` phase sheet supplies activity names and its `قیمت کل` values.
- Phase 01 land purchase cost is imported from the side information block and remains identifiable as land rather than construction cost.
- Duplicate activity labels within the same phase are disambiguated with their section title.
- The old pair-column budget template is still supported for backward compatibility.
- New empty project databases seed their phase/budget master from `phase_budget_current.xlsx` when present.
- Existing projects are not silently migrated; use the existing budget-import action to create a new budget version from the current workbook after reviewing the mapping.
