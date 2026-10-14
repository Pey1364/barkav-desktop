import tempfile
import threading
import time
import unittest
from pathlib import Path

from finance_db import FinanceDB
from sheet_sync import GoogleSheetsMirror
from telegram_stage5_workflow import TelegramStage5Workflow


class FakeCell:
    def __init__(self, row):
        self.row = row


class FakeWorksheet:
    def __init__(self, title):
        self.title = title
        self.rows = []

    def row_values(self, row):
        if 1 <= row <= len(self.rows):
            return list(self.rows[row - 1])
        return []

    def update(self, values, range_name=None, raw=True):
        row_num = 1
        if range_name and range_name.startswith("A"):
            left = range_name.split(":", 1)[0]
            digits = "".join(ch for ch in left if ch.isdigit())
            row_num = int(digits or 1)
        for offset, value_row in enumerate(values):
            target = row_num + offset
            while len(self.rows) < target:
                self.rows.append([])
            self.rows[target - 1] = list(value_row)
        return {}

    def clear(self):
        self.rows = []
        return {}

    def append_row(self, row, value_input_option="RAW"):
        self.rows.append(list(row))
        return {}

    def find(self, value, in_column=1):
        idx = in_column - 1
        for i, row in enumerate(self.rows, start=1):
            if idx < len(row) and str(row[idx]) == str(value):
                return FakeCell(i)
        return None


class FakeSpreadsheet:
    def __init__(self):
        self.sheets = {}

    def worksheet(self, title):
        if title not in self.sheets:
            raise KeyError(title)
        return self.sheets[title]

    def add_worksheet(self, title, rows, cols):
        ws = FakeWorksheet(title)
        self.sheets[title] = ws
        return ws


class FakeClient:
    def __init__(self, spreadsheet):
        self.spreadsheet = spreadsheet

    def open(self, name):
        return self.spreadsheet


class SheetSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = FinanceDB(Path(self.tmp.name) / "stage4.sqlite3")
        self.spreadsheet = FakeSpreadsheet()
        self.mirror = GoogleSheetsMirror(
            self.db,
            spreadsheet_name="TEST",
            credentials_file="unused.json",
            client_factory=lambda filename: FakeClient(self.spreadsheet),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_transaction_create_syncs_and_is_idempotent(self):
        tx = self.db.post_transaction(
            event_date="2026-08-10", direction="IN", amount=100_000_000,
            category="GENERAL_INCOME", description="واریزی شریک",
        )
        r1 = self.mirror.sync_batch()
        self.assertEqual(r1.synced, 1)
        ws = self.spreadsheet.sheets["V2-تراکنش‌ها"]
        self.assertEqual(len(ws.rows), 2)  # header + data
        self.assertEqual(ws.rows[1][0], tx)
        self.assertEqual(ws.rows[1][5], 100_000_000)
        r2 = self.mirror.sync_batch()
        self.assertEqual(r2.attempted, 0)
        self.assertEqual(len(ws.rows), 2)

    def test_void_updates_same_sheet_row_not_duplicate(self):
        tx = self.db.post_transaction(
            event_date="2026-08-10", direction="OUT", amount=20_000_000,
            category="NON_CONSTRUCTION_OUTFLOW", description="تست",
        )
        self.mirror.sync_batch()
        self.db.void_transaction(tx, reason="ثبت اشتباه")
        r = self.mirror.sync_batch()
        self.assertEqual(r.synced, 1)
        ws = self.spreadsheet.sheets["V2-تراکنش‌ها"]
        self.assertEqual(len(ws.rows), 2)
        self.assertEqual(ws.rows[1][14], "VOIDED")
        self.assertTrue(ws.rows[1][15])

    def test_expense_payment_cheque_use_separate_tabs(self):
        ex = self.db.create_expense(
            event_date="2026-08-10", final_amount=300_000_000,
            description="بتن", category="مصالح",
        )
        chq = self.db.create_cheque(
            expense_id=ex, amount=300_000_000, issue_date="2026-08-10",
            due_date="2026-09-10", due_date_shamsi="1405/06/19",
        )
        pay = self.db.add_payment(
            expense_id=ex, payment_date="2026-08-10", amount=300_000_000,
            method="CHEQUE", cheque_id=chq, status="PENDING",
        )
        r = self.mirror.sync_batch(limit=10)
        self.assertEqual(r.synced, 3)
        self.assertEqual(self.spreadsheet.sheets["V2-هزینه‌ها"].rows[1][0], ex)
        self.assertEqual(self.spreadsheet.sheets["V2-چک‌ها"].rows[1][0], chq)
        self.assertEqual(self.spreadsheet.sheets["V2-پرداخت‌ها"].rows[1][0], pay)

    def test_failed_connection_keeps_queue_for_retry(self):
        broken = GoogleSheetsMirror(
            self.db,
            spreadsheet_name="TEST",
            credentials_file="missing.json",
            client_factory=lambda filename: (_ for _ in ()).throw(ConnectionError("offline")),
        )
        self.db.post_transaction(
            event_date="2026-08-10", direction="IN", amount=1,
            category="TEST", description="offline",
        )
        r = broken.sync_batch()
        self.assertEqual(r.failed, 1)
        counts = self.db.sync_queue_counts()
        self.assertEqual(counts.get("FAILED"), 1)
        self.assertEqual(self.db.health_check()["pending_sync_items"], 1)

    def test_failed_item_retries_and_then_syncs(self):
        self.db.post_transaction(
            event_date="2026-08-10", direction="IN", amount=2,
            category="TEST", description="retry",
        )
        attempts = {"n": 0}
        def factory(filename):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ConnectionError("temporary")
            return FakeClient(self.spreadsheet)
        mirror = GoogleSheetsMirror(
            self.db, spreadsheet_name="TEST", credentials_file="unused", client_factory=factory,
        )
        self.assertEqual(mirror.sync_batch().failed, 1)
        result = mirror.sync_batch()
        self.assertEqual(result.synced, 1)
        self.assertEqual(result.remaining, 0)
        self.assertEqual(self.db.sync_queue_counts().get("SYNCED"), 1)

    def test_bootstrap_creates_all_four_tabs_even_without_cheques(self):
        titles = self.mirror.bootstrap_worksheets()
        self.assertEqual(set(titles), {
            "V2-تراکنش‌ها", "V2-هزینه‌ها", "V2-پرداخت‌ها", "V2-چک‌ها",
            "V2-واحدها", "V2-فروش‌ها", "V2-اقساط", "V2-وصول‌ها",
            "V2-وام‌ها", "V2-اقساط وام"
        })
        self.assertIn("V2-چک‌ها", self.spreadsheet.sheets)
        self.assertEqual(len(self.spreadsheet.sheets["V2-چک‌ها"].rows), 1)

    def test_concurrent_sync_calls_do_not_append_duplicate_transaction(self):
        tx = self.db.post_transaction(
            event_date="2026-08-10", direction="OUT", amount=100,
            category="TEST", description="race",
        )
        original_append = FakeWorksheet.append_row
        def slow_append(ws, row, value_input_option="RAW"):
            time.sleep(0.05)
            return original_append(ws, row, value_input_option=value_input_option)
        FakeWorksheet.append_row = slow_append
        try:
            results = []
            def run():
                results.append(self.mirror.sync_batch())
            t1 = threading.Thread(target=run)
            t2 = threading.Thread(target=run)
            t1.start(); t2.start(); t1.join(); t2.join()
        finally:
            FakeWorksheet.append_row = original_append
        ws = self.spreadsheet.sheets["V2-تراکنش‌ها"]
        ids = [row[0] for row in ws.rows[1:] if row]
        self.assertEqual(ids.count(tx), 1)
        self.assertEqual(sum(r.synced for r in results), 1)

    def test_rebuild_removes_duplicate_rows_and_creates_missing_tabs(self):
        tx = self.db.post_transaction(
            event_date="2026-08-10", direction="OUT", amount=100,
            category="TEST", description="repair",
        )
        self.mirror.sync_batch()
        ws = self.spreadsheet.sheets["V2-تراکنش‌ها"]
        ws.rows.append(list(ws.rows[1]))
        self.assertEqual(sum(1 for r in ws.rows[1:] if r and r[0] == tx), 2)
        counts = self.mirror.rebuild_all_from_sqlite()
        self.assertEqual(counts["transaction"], 1)
        ws = self.spreadsheet.sheets["V2-تراکنش‌ها"]
        self.assertEqual(sum(1 for r in ws.rows[1:] if r and r[0] == tx), 1)
        self.assertIn("V2-چک‌ها", self.spreadsheet.sheets)

    def test_stage5_edit_updates_same_sheet_rows_without_duplicates(self):
        flow = TelegramStage5Workflow(self.db)
        payload = {
            "detected_type": "EXPENSE", "document_type": "TEXT",
            "amount": 100_000_000, "invoice_amount": 100_000_000, "final_amount": 100_000_000,
            "paid_amount": 100_000_000, "payment_state": "PAID",
            "description": "بتن", "expense_category": "مصالح",
            "payment_method": "BANK_TRANSFER", "is_cheque": False,
            "manager_fee_eligible": True, "confidence": .99,
        }
        r = flow.receive_message(
            chat_id=-1001, message_id=900, raw_text="#تست بتن 100", content_type="TEXT",
            message_date="1405/05/19 12:00", analysis=payload,
        )
        first = flow.approve_and_post(r.pending_id).posting
        self.mirror.sync_batch(limit=20)
        edited = dict(payload)
        edited.update({"amount": 120_000_000, "invoice_amount": 120_000_000, "final_amount": 120_000_000, "paid_amount": 120_000_000})
        flow.begin_posted_revision(r.pending_id, edited)
        second = flow.approve_posted_revision(r.pending_id)
        self.assertEqual(first.expense_id, second.expense_id)
        self.assertEqual(first.transaction_id, second.transaction_id)
        self.mirror.sync_batch(limit=20)
        tx_ws = self.spreadsheet.sheets["V2-تراکنش‌ها"]
        ex_ws = self.spreadsheet.sheets["V2-هزینه‌ها"]
        self.assertEqual(sum(1 for row in tx_ws.rows[1:] if row and row[0] == first.transaction_id), 1)
        self.assertEqual(sum(1 for row in ex_ws.rows[1:] if row and row[0] == first.expense_id), 1)
        self.assertEqual(tx_ws.rows[1][5], 120_000_000)
        self.assertEqual(ex_ws.rows[1][8], 120_000_000)



if __name__ == "__main__":
    unittest.main()
