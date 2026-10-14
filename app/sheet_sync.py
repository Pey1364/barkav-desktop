from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from finance_db import FinanceDB

log = logging.getLogger("peymaan.sheets")


SHEET_DEFS: dict[str, tuple[str, list[str], list[str]]] = {
    "transaction": (
        "V2-تراکنش‌ها",
        [
            "ID", "تاریخ میلادی", "تاریخ شمسی", "ساعت", "جهت", "مبلغ (تومان)",
            "دسته", "پرداخت‌کننده", "گیرنده", "شرح", "منبع", "Expense ID",
            "Sale ID", "Loan ID", "وضعیت", "حذف/ابطال", "آخرین تغییر",
        ],
        [
            "transaction_id", "event_date", "shamsi_date", "event_time", "direction", "amount",
            "category", "payer_name", "receiver_name", "description", "source_type", "expense_id",
            "sale_id", "loan_id", "status", "deleted_at", "updated_at",
        ],
    ),
    "expense": (
        "V2-هزینه‌ها",
        [
            "ID", "تاریخ تحقق", "تاریخ شمسی", "فروشنده", "شرح", "دسته", "مرحله ساخت",
            "مبلغ فاکتور", "مبلغ نهایی", "تخفیف", "مشمول ۱۰٪", "وضعیت", "حذف/لغو", "آخرین تغییر",
        ],
        [
            "expense_id", "event_date", "shamsi_date", "vendor_name", "description", "category",
            "construction_stage", "invoice_amount", "final_amount", "discount_amount",
            "manager_fee_eligible", "status", "deleted_at", "updated_at",
        ],
    ),
    "payment": (
        "V2-پرداخت‌ها",
        [
            "ID", "Expense ID", "تاریخ پرداخت", "تاریخ شمسی", "مبلغ", "روش", "Transaction ID",
            "Cheque ID", "وضعیت", "شرح", "آخرین تغییر",
        ],
        [
            "payment_id", "expense_id", "payment_date", "payment_date_shamsi", "amount", "method",
            "transaction_id", "cheque_id", "status", "description", "updated_at",
        ],
    ),
    "unit": (
        "V2-واحدها",
        ["System ID", "ID واحد", "پروژه", "بلوک", "واحد", "طبقه", "متراژ", "ID پارکینگ", "پارکینگ", "ID انباری", "انباری", "وضعیت", "آخرین تغییر"],
        ["unit_id", "display_unit_id", "project_name", "block_name", "unit_number", "floor", "area", "parking_display_id", "parking", "storage_display_id", "storage", "status", "updated_at"],
    ),
    "sale": (
        "V2-فروش‌ها",
        ["ID", "Unit ID", "خریدار", "موبایل", "شماره قرارداد", "تاریخ قرارداد شمسی", "مبلغ قرارداد", "وضعیت", "توضیحات", "آخرین تغییر"],
        ["sale_id", "unit_id", "buyer_name", "buyer_phone", "contract_number", "contract_date_shamsi", "contract_amount", "status", "notes", "updated_at"],
    ),
    "installment": (
        "V2-اقساط",
        ["ID", "Sale ID", "شماره قسط", "سررسید شمسی", "مبلغ", "پرداخت‌شده", "مانده", "وضعیت", "شرح", "آخرین تغییر"],
        ["installment_id", "sale_id", "sequence_no", "due_date_shamsi", "amount", "paid_amount", "__remaining__", "status", "description", "updated_at"],
    ),
    "received_payment": (
        "V2-وصول‌ها",
        ["ID", "Sale ID", "Transaction ID", "مبلغ", "تاریخ وصول شمسی", "پرداخت‌کننده", "وضعیت تطبیق", "شرح", "آخرین تغییر"],
        ["received_payment_id", "sale_id", "transaction_id", "amount", "received_date_shamsi", "payer_name", "status", "description", "updated_at"],
    ),
    "loan": (
        "V2-وام‌ها",
        ["ID", "نوع وام", "بانک/وام‌دهنده", "اصل وام", "دریافتی واقعی", "تاریخ دریافت شمسی", "نرخ سود %", "کل سود", "کارمزد", "کل بازپرداخت", "تعداد اقساط", "مبلغ قسط", "اولین سررسید شمسی", "ضامنین", "وثیقه", "شماره قرارداد", "وضعیت", "توضیحات", "آخرین تغییر"],
        ["loan_id", "loan_type", "lender_name", "principal_amount", "net_received_amount", "received_date_shamsi", "interest_rate", "total_interest", "bank_fees", "total_repayment", "installment_count", "installment_amount", "first_due_date_shamsi", "guarantors", "collateral", "contract_number", "status", "description", "updated_at"],
    ),
    "loan_installment": (
        "V2-اقساط وام",
        ["ID", "Loan ID", "شماره قسط", "سررسید شمسی", "مبلغ", "اصل", "سود/کارمزد", "پرداخت‌شده", "تاریخ پرداخت شمسی", "Transaction ID", "وضعیت", "آخرین تغییر"],
        ["loan_installment_id", "loan_id", "installment_number", "due_date_shamsi", "amount", "principal_component", "interest_component", "paid_amount", "paid_date_shamsi", "transaction_id", "status", "updated_at"],
    ),
    "cheque": (
        "V2-چک‌ها",
        [
            "ID", "Expense ID", "مبلغ", "تاریخ صدور", "تاریخ صدور شمسی", "سررسید", "سررسید شمسی",
            "تاریخ پاس", "تاریخ پاس شمسی", "سریال/صیادی", "بانک", "صادرکننده", "نوع چک", "گیرنده", "شرح", "وضعیت",
            "Transaction پاس", "آخرین تغییر",
        ],
        [
            "cheque_id", "expense_id", "amount", "issue_date", "issue_date_shamsi", "due_date",
            "due_date_shamsi", "cashed_date", "cashed_date_shamsi", "cheque_serial", "issuer_bank",
            "issuer_name", "cheque_type", "receiver_name", "description", "status", "cash_transaction_id", "updated_at",
        ],
    ),
}


@dataclass(frozen=True)
class SyncBatchResult:
    attempted: int
    synced: int
    failed: int
    remaining: int
    last_error: str = ""


class GoogleSheetsMirror:
    """Idempotent SQLite -> Google Sheets mirror.

    Stage 4.1 adds a process-local synchronization lock. The background worker
    and the manual /sync command can no longer upsert the same queue item at the
    same time. This closes the find-then-append race that could create duplicate
    Sheet rows.
    """

    def __init__(
        self,
        db: FinanceDB,
        *,
        spreadsheet_name: str,
        credentials_file: str | Path,
        worksheet_prefix: str = "V2-",
        client_factory: Optional[Callable[[str], Any]] = None,
    ):
        self.db = db
        self.spreadsheet_name = str(spreadsheet_name)
        self.credentials_file = str(credentials_file)
        self.worksheet_prefix = worksheet_prefix
        self.client_factory = client_factory
        self._spreadsheet = None
        self._worksheets: dict[str, Any] = {}
        self._sync_lock = threading.RLock()

    def _default_client(self, filename: str):
        import gspread
        return gspread.service_account(filename=filename)

    def _connect(self):
        if self._spreadsheet is not None:
            return self._spreadsheet
        factory = self.client_factory or self._default_client
        client = factory(self.credentials_file)
        self._spreadsheet = client.open(self.spreadsheet_name)
        return self._spreadsheet

    def _sheet_title(self, entity_type: str) -> str:
        base = SHEET_DEFS[entity_type][0]
        if self.worksheet_prefix == "V2-":
            return base
        suffix = base.split("-", 1)[-1]
        return f"{self.worksheet_prefix}{suffix}"

    @staticmethod
    def _is_worksheet_not_found(exc: Exception) -> bool:
        name = exc.__class__.__name__
        text = str(exc).lower()
        return name in {"WorksheetNotFound", "KeyError", "LookupError"} or "worksheet not found" in text

    @staticmethod
    def _is_sheet_already_exists(exc: Exception) -> bool:
        text = str(exc).lower()
        return "already exists" in text or "همین نام" in text

    def _ensure_worksheet(self, entity_type: str):
        with self._sync_lock:
            if entity_type in self._worksheets:
                return self._worksheets[entity_type]
            spreadsheet = self._connect()
            title = self._sheet_title(entity_type)
            headers = SHEET_DEFS[entity_type][1]
            try:
                ws = spreadsheet.worksheet(title)
            except Exception as exc:
                if not self._is_worksheet_not_found(exc):
                    raise
                try:
                    ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=max(len(headers), 20))
                except Exception as add_exc:
                    # Defensive recovery if another caller/process created the tab
                    # between lookup and add.
                    if not self._is_sheet_already_exists(add_exc):
                        raise
                    ws = spreadsheet.worksheet(title)
            first = ws.row_values(1)
            if first[: len(headers)] != headers:
                last = self._col_letter(len(headers))
                ws.update(values=[headers], range_name=f"A1:{last}1", raw=True)
            self._worksheets[entity_type] = ws
            return ws

    def bootstrap_worksheets(self) -> list[str]:
        """Create/verify all V2 mirror tabs even when they contain no data yet."""
        with self._sync_lock:
            titles = []
            for entity_type in SHEET_DEFS:
                self._ensure_worksheet(entity_type)
                titles.append(self._sheet_title(entity_type))
            return titles

    @staticmethod
    def _col_letter(n: int) -> str:
        out = ""
        while n:
            n, rem = divmod(n - 1, 26)
            out = chr(65 + rem) + out
        return out

    @staticmethod
    def _cell_value(value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "بله" if value else "خیر"
        return value

    def _row_for(self, entity_type: str, entity: dict[str, Any]) -> list[Any]:
        fields = SHEET_DEFS[entity_type][2]
        row = []
        for field in fields:
            if field == "__remaining__":
                value = max(0, int(entity.get("amount") or 0) - int(entity.get("paid_amount") or 0))
            else:
                value = entity.get(field)
            if field == "manager_fee_eligible":
                value = "بله" if int(value or 0) else "خیر"
            row.append(self._cell_value(value))
        return row

    def _find_id_row(self, ws, entity_id: str) -> Optional[int]:
        try:
            cell = ws.find(entity_id, in_column=1)
            return int(cell.row) if cell else None
        except Exception as exc:
            if exc.__class__.__name__ in {"CellNotFound", "LookupError", "KeyError"}:
                return None
            if "not found" in str(exc).lower():
                return None
            raise

    def upsert_entity(self, entity_type: str, entity_id: str) -> None:
        with self._sync_lock:
            if entity_type not in SHEET_DEFS:
                raise ValueError(f"Unsupported sheet entity: {entity_type}")
            entity = self.db.get_entity_for_sync(entity_type, entity_id)
            if not entity:
                entity = {SHEET_DEFS[entity_type][2][0]: entity_id}
                entity["status"] = "DELETED"
            ws = self._ensure_worksheet(entity_type)
            row = self._row_for(entity_type, entity)
            row_number = self._find_id_row(ws, entity_id)
            if row_number is None:
                ws.append_row(row, value_input_option="RAW")
            else:
                last = self._col_letter(len(row))
                ws.update(values=[row], range_name=f"A{row_number}:{last}{row_number}", raw=True)

    def rebuild_all_from_sqlite(self) -> dict[str, int]:
        """Explicitly rebuild only the V2 mirror tabs from current SQLite state.

        This is the repair path for experimental duplicate Sheet rows. Production
        sheets outside the V2-* tabs are never touched.
        """
        with self._sync_lock:
            counts: dict[str, int] = {}
            self.bootstrap_worksheets()
            for entity_type in SHEET_DEFS:
                ws = self._ensure_worksheet(entity_type)
                headers = SHEET_DEFS[entity_type][1]
                entities = self.db.get_all_entities_for_sync(entity_type)
                rows = [headers] + [self._row_for(entity_type, entity) for entity in entities]
                if hasattr(ws, "clear"):
                    ws.clear()
                # One deterministic rewrite removes duplicates and also recreates
                # the correct header row.
                last = self._col_letter(len(headers))
                end_row = max(1, len(rows))
                ws.update(values=rows, range_name=f"A1:{last}{end_row}", raw=True)
                counts[entity_type] = len(entities)
            return counts

    def reset_connection(self) -> None:
        with self._sync_lock:
            self._spreadsheet = None
            self._worksheets.clear()

    def sync_batch(self, limit: int = 25) -> SyncBatchResult:
        # Entire queue read -> upsert -> status update is serialized. This is
        # essential because /sync and the background worker run in different
        # threads via asyncio.to_thread().
        with self._sync_lock:
            items = self.db.get_sync_items(limit=limit)
            if not items:
                return SyncBatchResult(0, 0, 0, 0, "")
            attempted = synced = failed = 0
            last_error = ""
            for item in items:
                attempted += 1
                try:
                    self.upsert_entity(item["entity_type"], item["entity_id"])
                except Exception as exc:
                    last_error = f"{exc.__class__.__name__}: {exc}"
                    self.db.mark_sync_failed(item["sync_id"], last_error)
                    failed += 1
                    self.reset_connection()
                    break
                else:
                    self.db.mark_sync_success(item["sync_id"])
                    synced += 1
            remaining = sum(self.db.sync_queue_counts().get(s, 0) for s in ("PENDING", "FAILED"))
            return SyncBatchResult(attempted, synced, failed, remaining, last_error)
