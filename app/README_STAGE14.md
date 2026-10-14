# Peymaan V2 — Stage 14
## Receipt Intelligence + GUI Approval Center

Stage 14 is based on the stable Stage 13 ledger. SQLite remains the sole source of truth.
No financial effect is created until a pending item is explicitly approved.

### What changed

- New GUI tab: **مرکز تأیید**
  - Telegram financial messages/photos arrive as PENDING first.
  - Review original message, local OCR text, AI fields, per-field confidence, conflicts and duplicate suggestions.
  - Edit fields before posting.
  - Approve/reject directly in GUI.
  - Optional approval channels: GUI only / Telegram private only / both.
  - GUI and Telegram use the same `pending_id`, so approving in either place closes the same item.
  - After GUI approval, the bot outbox applies 👍 to the original group message and updates the private review card when possible.

- Receipt archive
  - Original image is archived by SHA-256 under `data/receipt_archive/original`.
  - A processed copy is created only for OCR/AI under `data/receipt_archive/processed`.
  - The original is not overwritten.

- Receipt intelligence pipeline
  1. Archive immutable original.
  2. Rotate/normalize/contrast/sharpen image.
  3. Optional local OCR with Tesseract (`fas+eng`).
  4. Gemini Vision structured extraction when available.
  5. Deterministic comparison between caption, OCR and Vision.
  6. Per-field confidence.
  7. High-visibility conflict warnings.
  8. Duplicate suggestions by amount/description and exact image SHA-256.

- Safe duplicate/document handling
  - **🔗 اتصال به ثبت موجود** attaches a receipt/document to an existing Expense/Transaction/Cheque with **no new financial effect**.
  - This is intended for a receipt/factor that documents a ledger item already registered.

- Conservative learning rules
  - When the user corrects counterparty -> construction stage/category, Stage 14 can reuse that mapping later.
  - Amounts and dates are never learned as reusable aliases.

### Local OCR on Windows

Python package `pytesseract` is included in `requirements_stage14.txt`, but the Tesseract OCR application itself is external.
Stage 14 auto-detects these common Windows paths:

- `C:\Program Files\Tesseract-OCR\tesseract.exe`
- `C:\Program Files (x86)\Tesseract-OCR\tesseract.exe`

Install Persian language data (`fas`) plus English (`eng`).
If Tesseract is installed elsewhere, set environment variable:

```bat
set PEYMAAN_TESSERACT_CMD=C:\path\to\tesseract.exe
```

The program still starts when local OCR is unavailable. In that case Gemini Vision can still analyze the image when its API is reachable; if neither is available, the item remains in the GUI for manual review rather than being posted automatically.

Run the diagnostic:

```bat
python receipt_diagnostic.py
```

Test a real image:

```bat
python receipt_diagnostic.py "C:\path\to\receipt.jpg"
```

### Upgrade from Stage 13

1. Stop Stage 13.
2. Extract Stage 14 to a new folder.
3. Copy your real `secrets.local.json` from Stage 13.
4. Copy the complete `data` folder from Stage 13.
5. Install/update requirements:

```bat
python -m pip install -r requirements_stage14.txt
```

6. Run tests:

```bat
python -m unittest discover -s tests -v
python stage14_smoke_test.py
```

7. Start normally by double-clicking `Peymaan.bat`.

The database migrates in place to schema 11 and keeps all Stage 13 data.

### Recommended first real-world validation

Before importing the historical project expenses, send 20–30 representative real documents:
- bank transfer receipts,
- card-to-card receipts,
- invoices,
- photos taken at an angle,
- low-light receipts,
- Persian and mixed Persian/English receipts,
- a repeated/duplicate receipt.

For each sample, compare: amount, date, payer, receiver, document type, description, construction stage/category and duplicate warning. Keep human approval enabled during this validation period.
