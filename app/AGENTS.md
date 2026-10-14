# AGENTS.md — BARKAV / Peymaan Coding Rules

## 1) Project identity and current state

- Product: **BARKAV — Engineering & Construction**
- Application type: Persian RTL construction-project finance, estimating, document-AI, and project-control desktop application.
- Current working version: **18.7 Word Corrections + Theme Integration Candidate**
- Current roadmap step: **Step 1 — stabilize the final desktop version**
- Feature-freeze baseline: **18.6** (kept as an immutable reference in the sibling 18.6 folder)
- 18.7 scope is restricted to `اصلاحات18.6.docx` items and the two themes supplied under `new theme`. Do not add unrelated features.
- Do not redesign the application from scratch. Preserve the existing architecture and business behavior unless the user explicitly approves a change.

## 2) Active 18.7 execution path

Treat these as the active entry points for the current release:

1. `BARKAV_18.7.bat`
2. `launcher_stage18_7.py`
3. `project_center_stage18_7.py`
4. `project_runner_stage18_7.py`
5. `dashboard_stage18_7.py`
6. `ui_stage18_7.py`
7. `reports_stage18_7.py`
8. `financial_calendar_stage18_7.py`

The project is layered over older stages. Older files are inherited dependencies, not automatically the right place to edit.

### Rule for stage files

- Prefer changing the **active 18.7 layer** for version-specific fixes.
- Do **not** modify inherited `stage15`, `stage16`, `stage17`, `stage18_0`–`stage18_3` files merely because the active layer imports them.
- If a correct fix truly requires editing an inherited/core module, first explain why the active layer is insufficient.
- Any inherited/core modification must be narrow, regression-tested, and called out explicitly in the final change summary.
- Never perform a broad refactor across historical stage files unless the user explicitly requests a consolidation/refactor phase.

## 3) Source of truth documents

Before making a non-trivial change, read:

- `AGENTS.md`
- `handoff/BARKAV_PROJECT_HANDOFF.md`
- latest checkpoint under `handoff/checkpoints/`
- `source/VERSION.txt` or the equivalent active `VERSION.txt`
- current roadmap when present
- tests related to the requested feature

When documentation conflicts:
1. Active version files and latest checkpoint win over older handoff wording.
2. Explicit current user instructions win over all repository documentation.
3. Do not silently guess. Report the conflict.

Some older handoff files have stale version headings. Do not infer the active version from an old heading alone.

## 4) Non-negotiable financial/data invariants

These rules must not change unless the user explicitly requests an accounting-rule change:

- **SQLite is the financial source of truth.**
- Telegram and GUI must feed the same approval/accounting pipeline.
- Google Sheets, when used, is a mirror/reporting layer, not an independent accounting source of truth.
- AI-created/Pending data has **no final financial effect until human approval**.
- Financial deletion must remain audit-safe; use soft-delete/history rather than destructive deletion where the existing architecture requires it.
- Do not collapse distinct concepts:
  - execution date
  - invoice/cost-recognition date
  - registration date
  - payment date
  - cheque issue date
  - cheque due date
  - cheque clearing date
- Land purchase is project cost but is not construction cost.
- A non-construction `خروجی` reduces project cash but is not construction cost.
- Construction cost paid by cheque accrues when the obligation/work is realized. Later cheque clearing changes cash and must not create construction cost again.
- Manager-account withdrawals are not new construction cost.
- One cost may have multiple payments/documents.
- One payment may settle multiple invoices/costs.
- An invoice without an identified payment remains unpaid/debt.
- `بابت ضمانت` cheques are non-financial custody/security and must not become expense/outflow/payment/Actual.
- A cheque returned on condition of settlement (`عودتی به شرط تسویه`, stored as status `RETURNED` with
  `settlement_mode='RETURNED_ON_SETTLEMENT'`) counts with the cashed cheques (`پاس‌شده`): no debt remains through it,
  so it is no open cheque commitment, no due cheque of the next 30 days and no unpaid cheque on the dashboard. A plain
  `برگشتی` cheque is still owed. Every place that decides «open» or «cashed» asks `cheque_status187.py`
  (`is_open`, `counts_as_cashed`, `open_sql`); never repeat `status IN ('ISSUED','PENDING_DUE','RETURNED')`.
- Historical project data is learning/reference context only and must never post into current accounting.
- **RED LINE: no financial row without a Data Entry record.** Every cheque, expense, payment and cash
  transaction in the Transactions tabs is made by the approval of one Data Entry record and belongs to that
  record for as long as it is approved. A row is either owned by an approved record or it is taken back
  (cancelled / voided / deleted) and is no row of any tab; a row that is neither, and a taken-back row nothing
  refers to, are violations. Never write code that creates such a row outside an approval, and never let an
  approval, an edit, a rejection, «انتقال به دردست بررسی» or a restore leave one behind. Re-posting a record keeps
  its cheque on the row it already had (`FinanceDB._new_cheque_id`), so one cheque stays one row with one id.
  The definition and the check are in `record_ownership187.py`; the running app enforces it
  (`FinanceDB.enforce_record_context`, switched on in `project_runner_stage18_7.py`); `tests/test_red_line_ownership187.py`
  takes every kind of record through its whole life and fails on a violation. Code that works for a record but is
  not an approval wraps itself in `db.record_context(pending_id)`. Do not weaken this to make a test pass.

## 5) UI/product rules

- User-facing UI is primarily **Persian RTL**.
- Preserve the existing V15 functional backbone unless removal is explicitly approved.
- Do not create duplicate navigation/features that already exist.
- `هزینه` must remain visually/semantically expense; do not silently relabel it as `خروجی`.
- Preserve separate receipt evidence:
  - user caption/message
  - OCR/extracted text
- User-written context has higher semantic priority than irrelevant printed advertising/text inside images.
- A multi-line Persian box that people type in (a `tk.Text`: «بابت», the receipt text, a document's description) is
  taught by `rtl_text187.install(widget)`: Tk 8.6 draws the caret at the other end of right-to-left text, moves it to
  the start on a click and shuffles the words when it sits in the middle. The box keeps the caret at the end of its text
  and its lines inside an invisible right-to-left mark, so read it through `widget.get` (which drops the marks).
- Maintain Dark/Light compatibility where the active screen supports themes.
- Keep BARKAV branding as **BARKAV — Engineering & Construction**; do not add `Group`.

## 6) Security, privacy, and sensitive data

Never expose, print, commit, upload, package, or echo secret values.

### Never include in a development/public package

- `secrets.local.json`
- live SQLite databases
- autosave/runtime databases
- runtime logs containing sensitive values
- user receipt/contract/chat attachments unless explicitly requested and sanitized
- private historical chat exports containing real financial/personal data

### `secrets.local.json`

- Do not modify it unless the user explicitly asks.
- Do not display its contents in chat, terminal output, diffs, logs, screenshots, or generated reports.
- Code may validate that required keys exist, but must not log their values.

### Live `data/`

- Treat the user's live `data/` as production data.
- Do not run destructive tests against it.
- For migrations or risky operations, work on a copy.
- Before any future schema migration/update workflow, require a backup and a tested rollback/restore path.

### Historical learning data

If the full repository contains real WhatsApp/Telegram history or historical financial examples:
- treat them as private user data;
- do not add them to Git/public packages;
- prefer sanitized fixtures for tests and examples.

## 7) Project isolation

Each project must keep its financial SQLite isolated.

- Do not make two projects silently share the same database.
- `GROUP_CHAT_ID` uniqueness must be preserved across project creation **and project import/open**.
- `.barkav` project shortcuts are references to project data; validate them before registration/open.
- Do not silently rewrite a shortcut to another project/database.

## 8) AI/document processing rules

Keep extraction separate from accounting classification.

### Extraction may identify

- amount
- currency/unit
- dates
- payer/payee
- bank/reference
- line items
- visible text
- multiple documents in one image

### Classification may propose

- event type
- phase/activity
- payment state
- ranked candidates

Critical uncertainty such as Rial/Toman ambiguity, conflicting totals, unclear payee, or uncertain financial effect must remain reviewable by a human.

AI must not invent phase/activity names outside the official taxonomy.

## 9) Tests and regression discipline

Known 18.6 baseline:

- Default full suite: **224 passed, 34 GUI/package-gated skipped**
- Dedicated 18.6 regression tests: **16 passed**
- 18.6 GUI tests: **2 opt-in passed on Windows**, including manager calculation, currency rendering, filtered totals, roof/floor/team layout and report controls.
- Last confirmed inherited 18.4 GUI baseline: **218 passed, 0 failed**

### Before changing code

1. Identify the smallest relevant set of files.
2. Read the related existing tests.
3. Record the current test baseline when practical.

### After changing code

Run targeted tests first, then the full suite when the environment supports it.

Typical commands from the source root:

```bash
python -m pytest tests/test_stage18_5_regression.py -q
python -m pytest tests/test_stage18_5_ui.py -q
python -m pytest -q
```

If GUI tests require Xvfb/Linux or actual Windows behavior:
- clearly state what was and was not executed;
- never claim a Windows acceptance test passed unless it actually ran on Windows.

Any regression from the known baseline must be investigated before considering the task complete.

## 10) Windows acceptance items

Do not mark these as fully accepted based only on Linux/headless tests:

- Explorer shortcut icon rendering/cache
- live `.barkav` shortcuts
- opening live project DBs
- real Telegram connectivity
- real Gemini connectivity
- Windows DPI/font/rendering differences
- PDF/Printer behavior on the target Windows machine

## 11) Dependency policy

The current project inherits older requirements files.

- Do not casually upgrade dependencies.
- For the 18.6 stabilization candidate, prefer the tested pinned dependency set in `requirements_18.6.lock`.
- A dependency update is a code change: run regression tests after it.
- Avoid replacing working libraries without a concrete reason.

## 12) Exception and logging policy

The repository contains legacy best-effort exception handling.

For new or modified critical paths:
- do not add new silent `except Exception: pass` around finance, database, project registry, save, migration, Telegram routing, or document persistence;
- log actionable errors without logging secrets;
- show a useful user-facing error where appropriate;
- keep best-effort swallowing only for clearly non-critical cosmetic UI operations.

## 13) Known audit findings — do not auto-fix without a task

These are known items to keep in mind. Do not change them just because this file mentions them.

1. `launcher_stage18_4.py` has a weaker secrets/dependency preflight than 18.3.
2. `.barkav` import/open should enforce the same `GROUP_CHAT_ID` uniqueness rule as new-project creation.
3. Project Center 18.4 contains hard-coded dark styling and is not fully theme-driven.
4. Requirements are not fully pinned for a reproducible release.
5. Historical documentation contains stale version headings.
6. Attachment storage should be reviewed before future Save As / Portable / Backup architecture.
7. Many legacy broad exception handlers exist and should be reduced only in touched/critical paths, not via an uncontrolled global rewrite.

## 14) Scope control

For every task:

- Change only what is needed for the request.
- Do not “clean up” unrelated code.
- Do not rename public fields, database columns, Persian labels, transaction types, or files without a migration/compatibility reason.
- Do not change the database schema unless the user explicitly approves a schema change.
- Do not perform finance migrations as part of a UI task.
- Do not alter Telegram/Gemini behavior during unrelated UI work.
- Do not delete old stage files during normal 18.5/18.6 fixes.
- Avoid large-formatting-only diffs.

If you discover an unrelated bug:
- report it separately;
- do not fix it unless it blocks the requested task or the user approves.

## 15) Change completion checklist

Before reporting completion, provide:

1. What was changed.
2. Exact files changed.
3. Why each file needed to change.
4. Tests/commands actually run.
5. Test results.
6. Anything not tested.
7. Any database/schema impact.
8. Any privacy/security impact.
9. Any follow-up risk.

For risky changes, also provide a rollback instruction.

## 16) Preferred workflow for Codex

For a new task:

1. Read `AGENTS.md`.
2. Read current version/handoff/checkpoint.
3. Inspect the relevant implementation and tests.
4. Propose the smallest safe plan.
5. Make narrowly scoped edits.
6. Add/update tests for changed behavior.
7. Run targeted tests.
8. Run the full suite where possible.
9. Review the diff for unrelated changes and secrets.
10. Report results and remaining Windows/manual acceptance items.

## 17) Release direction

The immediate objective is **18.6 stabilization and live-data Windows acceptance after the GUI-focused pass**.

Do not start major architecture consolidation, cloud sync, mobile backend, role-based access, installer/updater redesign, or broad database migration unless the user explicitly moves the project to that roadmap step.

## 18) User worktree policy — 2026-10-05

For each new task/card, create a distinct task worktree and branch. Preserve
the main release checkout and other tasks' local state. At completion, ask
the user whether to remove that task's worktree and branch; do not delete
them automatically. Keep recoverable Git snapshots and preserve ignored
project data, databases, attachments and credentials before cleanup.
