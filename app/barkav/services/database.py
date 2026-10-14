from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA_VERSION = 13
DEFAULT_MANAGER_FEE_BPS = 1000  # 10.00%


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


@dataclass(frozen=True)
class FinancialSnapshot:
    cash_balance: int
    construction_cost: int
    manager_fee_accrued: int
    manager_withdrawals: int
    manager_balance: int
    open_cheque_commitments: int
    free_cash_after_cheques: int


@dataclass(frozen=True)
class ManagerExposure:
    start_date: str
    end_date: str
    creditor_days: int
    debtor_days: int
    neutral_days: int
    creditor_toman_days: int
    debtor_toman_days: int
    net_toman_days: int
    average_creditor_balance: int
    average_debtor_balance: int


class FinanceDB:
    """SQLite source-of-truth for Peyman V2.

    Monetary values are stored as positive integer TOMAN. Direction determines
    cash-flow sign. Derived balances are never persisted as mutable totals.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = NORMAL")
        return con

    @contextmanager
    def tx(self):
        con = self.connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    @contextmanager
    def read(self):
        """Read-only connection context that always closes the SQLite handle."""
        con = self.connect()
        try:
            yield con
        finally:
            con.close()

    def _initialize(self) -> None:
        with self.tx() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS expenses (
                    expense_id TEXT PRIMARY KEY,
                    event_date TEXT NOT NULL,
                    shamsi_date TEXT,
                    vendor_name TEXT,
                    description TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT 'OTHER',
                    construction_stage TEXT,
                    invoice_amount INTEGER NOT NULL DEFAULT 0 CHECK(invoice_amount >= 0),
                    final_amount INTEGER NOT NULL CHECK(final_amount >= 0),
                    discount_amount INTEGER NOT NULL DEFAULT 0 CHECK(discount_amount >= 0),
                    manager_fee_eligible INTEGER NOT NULL DEFAULT 1 CHECK(manager_fee_eligible IN (0,1)),
                    status TEXT NOT NULL DEFAULT 'APPROVED' CHECK(status IN ('DRAFT','APPROVED','PARTIALLY_PAID','PAID','CANCELLED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    event_date TEXT NOT NULL,
                    shamsi_date TEXT,
                    event_time TEXT,
                    direction TEXT NOT NULL CHECK(direction IN ('IN','OUT')),
                    amount INTEGER NOT NULL CHECK(amount >= 0),
                    category TEXT NOT NULL,
                    payer_name TEXT,
                    receiver_name TEXT,
                    description TEXT NOT NULL DEFAULT '',
                    source_type TEXT NOT NULL DEFAULT 'SYSTEM',
                    telegram_chat_id INTEGER,
                    telegram_message_id INTEGER,
                    expense_id TEXT REFERENCES expenses(expense_id),
                    sale_id TEXT,
                    loan_id TEXT,
                    status TEXT NOT NULL DEFAULT 'POSTED' CHECK(status IN ('POSTED','VOIDED')),
                    sync_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(sync_status IN ('PENDING','SYNCED','FAILED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_transactions_event_date ON transactions(event_date);
                CREATE INDEX IF NOT EXISTS idx_transactions_expense ON transactions(expense_id);
                CREATE INDEX IF NOT EXISTS idx_transactions_sync ON transactions(sync_status);

                CREATE TABLE IF NOT EXISTS cheques (
                    cheque_id TEXT PRIMARY KEY,
                    expense_id TEXT REFERENCES expenses(expense_id),
                    amount INTEGER NOT NULL CHECK(amount >= 0),
                    issue_date TEXT NOT NULL,
                    issue_date_shamsi TEXT,
                    due_date TEXT NOT NULL,
                    due_date_shamsi TEXT,
                    cashed_date TEXT,
                    cashed_date_shamsi TEXT,
                    cheque_serial TEXT,
                    issuer_bank TEXT,
                    issuer_name TEXT,
                    cheque_type TEXT NOT NULL DEFAULT 'PHYSICAL',
                    registration_state TEXT NOT NULL DEFAULT 'UNREGISTERED',
                    is_guarantee INTEGER NOT NULL DEFAULT 0,
                    guarantee_status TEXT NOT NULL DEFAULT 'HELD',
                    settlement_mode TEXT NOT NULL DEFAULT 'NORMAL',
                    receiver_name TEXT,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'ISSUED' CHECK(status IN ('ISSUED','PENDING_DUE','CASHED','RETURNED','CANCELLED')),
                    cash_transaction_id TEXT REFERENCES transactions(transaction_id),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS payments (
                    payment_id TEXT PRIMARY KEY,
                    expense_id TEXT NOT NULL REFERENCES expenses(expense_id),
                    payment_date TEXT NOT NULL,
                    payment_date_shamsi TEXT,
                    amount INTEGER NOT NULL CHECK(amount >= 0),
                    method TEXT NOT NULL CHECK(method IN ('CASH','BANK_TRANSFER','CARD','CHEQUE','OTHER')),
                    transaction_id TEXT REFERENCES transactions(transaction_id),
                    cheque_id TEXT REFERENCES cheques(cheque_id),
                    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','COMPLETED','CANCELLED')),
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_payments_expense ON payments(expense_id);

                CREATE TABLE IF NOT EXISTS attachments (
                    attachment_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    document_type TEXT NOT NULL DEFAULT 'OTHER',
                    telegram_file_id TEXT,
                    telegram_file_unique_id TEXT,
                    telegram_chat_id INTEGER,
                    telegram_message_id INTEGER,
                    local_path TEXT,
                    mime_type TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS telegram_messages (
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    raw_text TEXT NOT NULL DEFAULT '',
                    content_type TEXT NOT NULL DEFAULT 'TEXT',
                    message_date TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'RECEIVED' CHECK(state IN ('RECEIVED','ANALYZED','PENDING_REVIEW','NEEDS_REVIEW','APPROVED','REJECTED','EDIT_PENDING','DELETED')),
                    private_review_message_id INTEGER,
                    linked_entity_type TEXT,
                    linked_entity_id TEXT,
                    reaction_state TEXT NOT NULL DEFAULT 'NONE' CHECK(reaction_state IN ('NONE','CHECKED')),
                    edited_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(chat_id, message_id)
                );

                CREATE TABLE IF NOT EXISTS pending_items (
                    pending_id TEXT PRIMARY KEY,
                    telegram_chat_id INTEGER NOT NULL,
                    telegram_message_id INTEGER NOT NULL,
                    detected_type TEXT,
                    payload_json TEXT NOT NULL,
                    confidence REAL,
                    status TEXT NOT NULL DEFAULT 'PENDING_REVIEW' CHECK(status IN ('PENDING_REVIEW','NEEDS_REVIEW','APPROVED','REJECTED','EDIT_PENDING')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(telegram_chat_id, telegram_message_id)
                );

                CREATE TABLE IF NOT EXISTS receipt_analyses (
                    analysis_id TEXT PRIMARY KEY,
                    pending_id TEXT NOT NULL UNIQUE REFERENCES pending_items(pending_id) ON DELETE CASCADE,
                    provider TEXT NOT NULL DEFAULT 'UNKNOWN',
                    document_type TEXT NOT NULL DEFAULT 'OTHER',
                    image_path TEXT,
                    image_sha256 TEXT,
                    ocr_text TEXT NOT NULL DEFAULT '',
                    raw_ai_json TEXT,
                    field_confidences_json TEXT NOT NULL DEFAULT '{}',
                    conflicts_json TEXT NOT NULL DEFAULT '[]',
                    duplicate_candidates_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'ANALYZED' CHECK(status IN ('ANALYZED','NEEDS_REVIEW','APPROVED','REJECTED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_receipt_analyses_status
                    ON receipt_analyses(status, updated_at);

                CREATE TABLE IF NOT EXISTS integration_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    pending_id TEXT REFERENCES pending_items(pending_id),
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','PROCESSING','DONE','FAILED')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_integration_events_status
                    ON integration_events(status, created_at);

                CREATE TABLE IF NOT EXISTS learned_rules (
                    rule_id TEXT PRIMARY KEY,
                    rule_type TEXT NOT NULL,
                    pattern TEXT NOT NULL,
                    target_field TEXT NOT NULL,
                    target_value TEXT NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(rule_type, pattern, target_field, target_value)
                );

                CREATE TABLE IF NOT EXISTS units (
                    unit_id TEXT PRIMARY KEY,
                    project_name TEXT,
                    block_name TEXT,
                    unit_number TEXT NOT NULL,
                    floor TEXT,
                    area REAL,
                    parking TEXT,
                    storage TEXT,
                    status TEXT NOT NULL DEFAULT 'AVAILABLE' CHECK(status IN ('AVAILABLE','RESERVED','SOLD','CANCELLED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    parking_id TEXT,
                    storage_id TEXT,
                    notes TEXT NOT NULL DEFAULT '',
                    display_unit_id TEXT,
                    parking_display_id TEXT,
                    storage_display_id TEXT
                );

                CREATE TABLE IF NOT EXISTS sales (
                    sale_id TEXT PRIMARY KEY,
                    unit_id TEXT NOT NULL REFERENCES units(unit_id),
                    buyer_name TEXT NOT NULL,
                    contract_number TEXT,
                    contract_date TEXT NOT NULL,
                    contract_date_shamsi TEXT,
                    contract_amount INTEGER NOT NULL CHECK(contract_amount >= 0),
                    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','COMPLETED','CANCELLED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS installments (
                    installment_id TEXT PRIMARY KEY,
                    sale_id TEXT NOT NULL REFERENCES sales(sale_id),
                    due_date TEXT NOT NULL,
                    due_date_shamsi TEXT,
                    amount INTEGER NOT NULL CHECK(amount >= 0),
                    paid_amount INTEGER NOT NULL DEFAULT 0 CHECK(paid_amount >= 0),
                    status TEXT NOT NULL DEFAULT 'UPCOMING' CHECK(status IN ('UPCOMING','DUE','PARTIALLY_PAID','PAID','OVERDUE','CANCELLED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS received_payments (
                    received_payment_id TEXT PRIMARY KEY,
                    sale_id TEXT NOT NULL REFERENCES sales(sale_id),
                    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
                    amount INTEGER NOT NULL CHECK(amount >= 0),
                    received_date TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'UNMATCHED' CHECK(status IN ('UNMATCHED','MATCHED','CANCELLED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS loans (
                    loan_id TEXT PRIMARY KEY,
                    lender_name TEXT NOT NULL,
                    principal_amount INTEGER NOT NULL CHECK(principal_amount >= 0),
                    received_date TEXT,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','CLOSED','CANCELLED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    loan_type TEXT NOT NULL DEFAULT 'BANK',
                    net_received_amount INTEGER NOT NULL DEFAULT 0,
                    received_date_shamsi TEXT,
                    interest_rate REAL NOT NULL DEFAULT 0,
                    total_interest INTEGER NOT NULL DEFAULT 0,
                    bank_fees INTEGER NOT NULL DEFAULT 0,
                    total_repayment INTEGER NOT NULL DEFAULT 0,
                    installment_count INTEGER NOT NULL DEFAULT 0,
                    installment_amount INTEGER NOT NULL DEFAULT 0,
                    first_due_date TEXT,
                    first_due_date_shamsi TEXT,
                    guarantors TEXT NOT NULL DEFAULT '',
                    collateral TEXT NOT NULL DEFAULT '',
                    contract_number TEXT NOT NULL DEFAULT '',
                    receive_transaction_id TEXT
                );

                CREATE TABLE IF NOT EXISTS loan_installments (
                    loan_installment_id TEXT PRIMARY KEY,
                    loan_id TEXT NOT NULL REFERENCES loans(loan_id),
                    installment_number INTEGER NOT NULL,
                    due_date TEXT NOT NULL,
                    due_date_shamsi TEXT,
                    amount INTEGER NOT NULL CHECK(amount >= 0),
                    principal_component INTEGER NOT NULL DEFAULT 0,
                    interest_component INTEGER NOT NULL DEFAULT 0,
                    paid_amount INTEGER NOT NULL DEFAULT 0,
                    paid_date TEXT,
                    paid_date_shamsi TEXT,
                    transaction_id TEXT REFERENCES transactions(transaction_id),
                    status TEXT NOT NULL DEFAULT 'UPCOMING' CHECK(status IN ('UPCOMING','DUE','PARTIALLY_PAID','PAID','OVERDUE','CANCELLED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(loan_id, installment_number)
                );

                CREATE TABLE IF NOT EXISTS receivables (
                    receivable_id TEXT PRIMARY KEY,
                    counterparty_name TEXT NOT NULL,
                    original_amount INTEGER NOT NULL CHECK(original_amount >= 0),
                    due_date TEXT,
                    related_transaction_id TEXT REFERENCES transactions(transaction_id),
                    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','PARTIALLY_PAID','PAID','CANCELLED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    reminder_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    channel_telegram INTEGER NOT NULL DEFAULT 1 CHECK(channel_telegram IN (0,1)),
                    channel_email INTEGER NOT NULL DEFAULT 0 CHECK(channel_email IN (0,1)),
                    status TEXT NOT NULL DEFAULT 'SCHEDULED' CHECK(status IN ('SCHEDULED','SENT','RESOLVED','CANCELLED','FAILED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reminder_log (
                    reminder_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reminder_id TEXT NOT NULL REFERENCES reminders(reminder_id),
                    sent_at TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    success INTEGER NOT NULL CHECK(success IN (0,1)),
                    details TEXT
                );

                CREATE TABLE IF NOT EXISTS reconciliations (
                    reconciliation_id TEXT PRIMARY KEY,
                    event_date TEXT NOT NULL,
                    shamsi_date TEXT,
                    system_balance INTEGER NOT NULL,
                    bank_balance INTEGER NOT NULL,
                    difference INTEGER NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sync_queue (
                    sync_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    operation TEXT NOT NULL CHECK(operation IN ('CREATE','UPDATE','DELETE')),
                    payload_json TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','SYNCED','FAILED')),
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sync_queue_status ON sync_queue(status, sync_id);

                CREATE TABLE IF NOT EXISTS audit_log (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    source TEXT NOT NULL,
                    before_json TEXT,
                    after_json TEXT,
                    actor_id TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS financial_postings (
                    posting_id TEXT PRIMARY KEY,
                    pending_id TEXT NOT NULL UNIQUE REFERENCES pending_items(pending_id),
                    posting_type TEXT NOT NULL,
                    primary_entity_type TEXT,
                    primary_entity_id TEXT,
                    expense_id TEXT REFERENCES expenses(expense_id),
                    transaction_id TEXT REFERENCES transactions(transaction_id),
                    payment_id TEXT REFERENCES payments(payment_id),
                    cheque_id TEXT REFERENCES cheques(cheque_id),
                    plan_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS posting_revisions (
                    revision_id TEXT PRIMARY KEY,
                    pending_id TEXT NOT NULL REFERENCES pending_items(pending_id),
                    old_payload_json TEXT NOT NULL,
                    new_payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','APPROVED','REJECTED')),
                    source TEXT NOT NULL DEFAULT 'PRIVATE_EDIT',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_posting_revisions_pending
                    ON posting_revisions(pending_id, status, created_at);
                """
            )
            # Lightweight in-place migration from Stage 4 databases.
            columns = {r[1] for r in con.execute("PRAGMA table_info(financial_postings)").fetchall()}
            if "status" not in columns:
                con.execute("ALTER TABLE financial_postings ADD COLUMN status TEXT NOT NULL DEFAULT 'ACTIVE'")
            if "updated_at" not in columns:
                con.execute("ALTER TABLE financial_postings ADD COLUMN updated_at TEXT")
                con.execute("UPDATE financial_postings SET updated_at=created_at WHERE updated_at IS NULL")
            if "deleted_at" not in columns:
                con.execute("ALTER TABLE financial_postings ADD COLUMN deleted_at TEXT")

            loan_cols = {r[1] for r in con.execute("PRAGMA table_info(loans)").fetchall()}
            loan_additions = {
                "loan_type": "TEXT NOT NULL DEFAULT 'BANK'",
                "net_received_amount": "INTEGER NOT NULL DEFAULT 0",
                "received_date_shamsi": "TEXT",
                "interest_rate": "REAL NOT NULL DEFAULT 0",
                "total_interest": "INTEGER NOT NULL DEFAULT 0",
                "bank_fees": "INTEGER NOT NULL DEFAULT 0",
                "total_repayment": "INTEGER NOT NULL DEFAULT 0",
                "installment_count": "INTEGER NOT NULL DEFAULT 0",
                "installment_amount": "INTEGER NOT NULL DEFAULT 0",
                "first_due_date": "TEXT",
                "first_due_date_shamsi": "TEXT",
                "guarantors": "TEXT NOT NULL DEFAULT ''",
                "collateral": "TEXT NOT NULL DEFAULT ''",
                "contract_number": "TEXT NOT NULL DEFAULT ''",
                "receive_transaction_id": "TEXT",
            }
            for col, ddl in loan_additions.items():
                if col not in loan_cols:
                    con.execute(f"ALTER TABLE loans ADD COLUMN {col} {ddl}")

            unit_cols = {r[1] for r in con.execute("PRAGMA table_info(units)").fetchall()}
            unit_additions = {
                'parking_id': 'TEXT',
                'storage_id': 'TEXT',
                'notes': "TEXT NOT NULL DEFAULT ''",
                'display_unit_id': 'TEXT',
                'parking_display_id': 'TEXT',
                'storage_display_id': 'TEXT',
            }
            for col, ddl in unit_additions.items():
                if col not in unit_cols:
                    con.execute(f"ALTER TABLE units ADD COLUMN {col} {ddl}")

            cheque_cols = {r[1] for r in con.execute("PRAGMA table_info(cheques)").fetchall()}
            if 'issuer_name' not in cheque_cols:
                con.execute("ALTER TABLE cheques ADD COLUMN issuer_name TEXT")
            if 'cheque_type' not in cheque_cols:
                con.execute("ALTER TABLE cheques ADD COLUMN cheque_type TEXT NOT NULL DEFAULT 'PHYSICAL'")
            if 'registration_state' not in cheque_cols:
                con.execute("ALTER TABLE cheques ADD COLUMN registration_state TEXT NOT NULL DEFAULT 'UNREGISTERED'")
            else:
                con.execute("UPDATE cheques SET registration_state='UNREGISTERED' WHERE registration_state IS NULL OR registration_state='' OR registration_state='UNKNOWN'")
            if 'is_guarantee' not in cheque_cols:
                con.execute("ALTER TABLE cheques ADD COLUMN is_guarantee INTEGER NOT NULL DEFAULT 0")
            if 'guarantee_status' not in cheque_cols:
                con.execute("ALTER TABLE cheques ADD COLUMN guarantee_status TEXT NOT NULL DEFAULT 'HELD'")
            if 'settlement_mode' not in cheque_cols:
                con.execute("ALTER TABLE cheques ADD COLUMN settlement_mode TEXT NOT NULL DEFAULT 'NORMAL'")

            rec_cols = {r[1] for r in con.execute("PRAGMA table_info(reconciliations)").fetchall()}
            if 'updated_at' not in rec_cols:
                con.execute("ALTER TABLE reconciliations ADD COLUMN updated_at TEXT")
                con.execute("UPDATE reconciliations SET updated_at=created_at WHERE updated_at IS NULL")
            if 'deleted_at' not in rec_cols:
                con.execute("ALTER TABLE reconciliations ADD COLUMN deleted_at TEXT")

            con.execute(
                "INSERT OR REPLACE INTO app_meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            con.execute(
                "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES('manager_fee_bps', ?, ?)",
                (str(DEFAULT_MANAGER_FEE_BPS), _now()),
            )
            con.execute(
                "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES('currency', 'TOMAN', ?)",
                (_now(),),
            )
            con.execute(
                "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES('approval_channels', 'BOTH', ?)",
                (_now(),),
            )
            con.execute(
                "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES('receipt_local_ocr_enabled', '1', ?)",
                (_now(),),
            )

    # ---------- settings ----------
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self.read() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.tx() as con:
            con.execute(
                "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, str(value), _now()),
            )

    # ---------- audit/sync ----------
    def _audit(self, con: sqlite3.Connection, entity_type: str, entity_id: str, action: str,
               source: str, before: Optional[dict] = None, after: Optional[dict] = None,
               actor_id: Optional[str] = None) -> None:
        con.execute(
            "INSERT INTO audit_log(entity_type,entity_id,action,source,before_json,after_json,actor_id,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                entity_type, entity_id, action, source,
                json.dumps(before, ensure_ascii=False) if before is not None else None,
                json.dumps(after, ensure_ascii=False) if after is not None else None,
                actor_id, _now(),
            ),
        )

    def _enqueue_sync(self, con: sqlite3.Connection, entity_type: str, entity_id: str,
                      operation: str, payload: Optional[dict] = None) -> None:
        con.execute(
            "INSERT INTO sync_queue(entity_type,entity_id,operation,payload_json,status,created_at,updated_at) "
            "VALUES(?,?,?,?, 'PENDING', ?, ?)",
            (
                entity_type, entity_id, operation,
                json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                _now(), _now(),
            ),
        )



    def get_sync_items(self, limit: int = 25) -> list[dict[str, Any]]:
        """Return unsynced queue items in deterministic order.

        FAILED items are intentionally retried. The Google Sheets mirror is a
        projection of current SQLite state, so replaying an old event is safe:
        the synchronizer always upserts the entity's latest row by stable ID.
        """
        limit = max(1, int(limit))
        with self.read() as con:
            rows = con.execute(
                "SELECT * FROM sync_queue WHERE status IN ('PENDING','FAILED') ORDER BY sync_id LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            raw = item.get("payload_json")
            try:
                item["payload"] = json.loads(raw) if raw else None
            except Exception:
                item["payload"] = None
            result.append(item)
        return result

    def sync_queue_counts(self) -> dict[str, int]:
        with self.read() as con:
            rows = con.execute("SELECT status, COUNT(*) c FROM sync_queue GROUP BY status").fetchall()
        return {r["status"]: int(r["c"]) for r in rows}

    def get_entity_for_sync(self, entity_type: str, entity_id: str) -> Optional[dict[str, Any]]:
        tables = {
            "transaction": ("transactions", "transaction_id"),
            "expense": ("expenses", "expense_id"),
            "payment": ("payments", "payment_id"),
            "cheque": ("cheques", "cheque_id"),
            "unit": ("units", "unit_id"),
            "sale": ("sales", "sale_id"),
            "installment": ("installments", "installment_id"),
            "received_payment": ("received_payments", "received_payment_id"),
            "loan": ("loans", "loan_id"),
            "loan_installment": ("loan_installments", "loan_installment_id"),
        }
        if entity_type not in tables:
            return None
        table, pk = tables[entity_type]
        with self.read() as con:
            row = con.execute(f"SELECT * FROM {table} WHERE {pk}=?", (entity_id,)).fetchone()
            return dict(row) if row else None

    def get_all_entities_for_sync(self, entity_type: str) -> list[dict[str, Any]]:
        """Return the complete current SQLite projection for one mirror entity type.

        Used only by the explicit V2 Sheets rebuild command. SQLite remains the
        source of truth, so rebuilding a V2 tab from these rows is safe.
        """
        tables = {
            "transaction": ("transactions", "transaction_id"),
            "expense": ("expenses", "expense_id"),
            "payment": ("payments", "payment_id"),
            "cheque": ("cheques", "cheque_id"),
            "unit": ("units", "unit_id"),
            "sale": ("sales", "sale_id"),
            "installment": ("installments", "installment_id"),
            "received_payment": ("received_payments", "received_payment_id"),
            "loan": ("loans", "loan_id"),
            "loan_installment": ("loan_installments", "loan_installment_id"),
        }
        if entity_type not in tables:
            return []
        table, pk = tables[entity_type]
        with self.read() as con:
            rows = con.execute(f"SELECT * FROM {table} ORDER BY {pk}").fetchall()
        return [dict(row) for row in rows]

    def get_latest_telegram_message(self, chat_id: int) -> Optional[dict[str, Any]]:
        with self.read() as con:
            row = con.execute(
                "SELECT * FROM telegram_messages WHERE chat_id=? ORDER BY message_id DESC LIMIT 1",
                (int(chat_id),),
            ).fetchone()
            return dict(row) if row else None

    def mark_sync_success(self, sync_id: int) -> None:
        now = _now()
        with self.tx() as con:
            row = con.execute("SELECT entity_type,entity_id FROM sync_queue WHERE sync_id=?", (int(sync_id),)).fetchone()
            if not row:
                return
            con.execute(
                "UPDATE sync_queue SET status='SYNCED', last_error=NULL, updated_at=? WHERE sync_id=?",
                (now, int(sync_id)),
            )
            if row["entity_type"] == "transaction":
                remaining = con.execute(
                    "SELECT 1 FROM sync_queue WHERE entity_type='transaction' AND entity_id=? AND status!='SYNCED' LIMIT 1",
                    (row["entity_id"],),
                ).fetchone()
                con.execute(
                    "UPDATE transactions SET sync_status=?, updated_at=updated_at WHERE transaction_id=?",
                    ("PENDING" if remaining else "SYNCED", row["entity_id"]),
                )

    def mark_sync_failed(self, sync_id: int, error: str) -> None:
        now = _now()
        msg = (error or "Unknown sync error")[:1500]
        with self.tx() as con:
            row = con.execute("SELECT entity_type,entity_id FROM sync_queue WHERE sync_id=?", (int(sync_id),)).fetchone()
            if not row:
                return
            con.execute(
                "UPDATE sync_queue SET status='FAILED', retry_count=retry_count+1, last_error=?, updated_at=? WHERE sync_id=?",
                (msg, now, int(sync_id)),
            )
            if row["entity_type"] == "transaction":
                con.execute(
                    "UPDATE transactions SET sync_status='FAILED' WHERE transaction_id=?",
                    (row["entity_id"],),
                )

    def reset_failed_sync(self) -> int:
        with self.tx() as con:
            cur = con.execute(
                "UPDATE sync_queue SET status='PENDING', last_error=NULL, updated_at=? WHERE status='FAILED'",
                (_now(),),
            )
            con.execute("UPDATE transactions SET sync_status='PENDING' WHERE sync_status='FAILED'")
            return int(cur.rowcount)

    # ---------- telegram review workflow ----------
    def register_telegram_message(self, *, chat_id: int, message_id: int, raw_text: str,
                                  content_type: str, message_date: str,
                                  state: str = "RECEIVED") -> bool:
        """Insert a Telegram source message once.

        Returns True when a new row was created and False for an existing message.
        The (chat_id, message_id) primary key is the first duplicate-protection layer.
        """
        now = _now()
        with self.tx() as con:
            cur = con.execute(
                """INSERT OR IGNORE INTO telegram_messages(
                    chat_id,message_id,raw_text,content_type,message_date,state,
                    reaction_state,created_at,updated_at
                ) VALUES(?,?,?,?,?,?, 'NONE', ?, ?)""",
                (int(chat_id), int(message_id), raw_text or "", content_type, message_date, state, now, now),
            )
            return cur.rowcount == 1

    def get_telegram_message(self, chat_id: int, message_id: int) -> Optional[dict[str, Any]]:
        with self.read() as con:
            row = con.execute(
                "SELECT * FROM telegram_messages WHERE chat_id=? AND message_id=?",
                (int(chat_id), int(message_id)),
            ).fetchone()
            return dict(row) if row else None

    def update_telegram_message(self, *, chat_id: int, message_id: int,
                                raw_text: Optional[str] = None,
                                state: Optional[str] = None,
                                private_review_message_id: Optional[int] = None,
                                linked_entity_type: Optional[str] = None,
                                linked_entity_id: Optional[str] = None,
                                reaction_state: Optional[str] = None,
                                mark_edited: bool = False) -> None:
        fields: list[str] = []
        values: list[Any] = []
        for col, value in [
            ("raw_text", raw_text), ("state", state),
            ("private_review_message_id", private_review_message_id),
            ("linked_entity_type", linked_entity_type), ("linked_entity_id", linked_entity_id),
            ("reaction_state", reaction_state),
        ]:
            if value is not None:
                fields.append(f"{col}=?")
                values.append(value)
        if mark_edited:
            fields.append("edited_at=?")
            values.append(_now())
        fields.append("updated_at=?")
        values.append(_now())
        values.extend([int(chat_id), int(message_id)])
        with self.tx() as con:
            cur = con.execute(
                f"UPDATE telegram_messages SET {', '.join(fields)} WHERE chat_id=? AND message_id=?",
                values,
            )
            if cur.rowcount == 0:
                raise KeyError((chat_id, message_id))

    def create_or_replace_pending(self, *, telegram_chat_id: int, telegram_message_id: int,
                                  detected_type: Optional[str], payload: dict[str, Any],
                                  confidence: Optional[float] = None,
                                  status: str = "PENDING_REVIEW") -> str:
        now = _now()
        with self.tx() as con:
            old = con.execute(
                "SELECT pending_id FROM pending_items WHERE telegram_chat_id=? AND telegram_message_id=?",
                (int(telegram_chat_id), int(telegram_message_id)),
            ).fetchone()
            if old:
                pending_id = old["pending_id"]
                con.execute(
                    """UPDATE pending_items SET detected_type=?, payload_json=?, confidence=?,
                    status=?, updated_at=? WHERE pending_id=?""",
                    (detected_type, json.dumps(payload, ensure_ascii=False), confidence, status, now, pending_id),
                )
            else:
                pending_id = _id("PEN")
                con.execute(
                    """INSERT INTO pending_items(
                        pending_id,telegram_chat_id,telegram_message_id,detected_type,
                        payload_json,confidence,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (pending_id, int(telegram_chat_id), int(telegram_message_id), detected_type,
                     json.dumps(payload, ensure_ascii=False), confidence, status, now, now),
                )
            return pending_id

    def get_pending_item(self, pending_id: str) -> Optional[dict[str, Any]]:
        with self.read() as con:
            row = con.execute("SELECT * FROM pending_items WHERE pending_id=?", (pending_id,)).fetchone()
            if not row:
                return None
            out = dict(row)
            out["payload"] = json.loads(out.pop("payload_json"))
            return out

    def get_pending_by_message(self, chat_id: int, message_id: int) -> Optional[dict[str, Any]]:
        with self.read() as con:
            row = con.execute(
                "SELECT * FROM pending_items WHERE telegram_chat_id=? AND telegram_message_id=?",
                (int(chat_id), int(message_id)),
            ).fetchone()
            if not row:
                return None
            out = dict(row)
            out["payload"] = json.loads(out.pop("payload_json"))
            return out

    def update_pending(self, pending_id: str, *, payload: Optional[dict[str, Any]] = None,
                       detected_type: Optional[str] = None,
                       confidence: Optional[float] = None,
                       status: Optional[str] = None) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if payload is not None:
            fields.append("payload_json=?")
            values.append(json.dumps(payload, ensure_ascii=False))
        if detected_type is not None:
            fields.append("detected_type=?")
            values.append(detected_type)
        if confidence is not None:
            fields.append("confidence=?")
            values.append(float(confidence))
        if status is not None:
            fields.append("status=?")
            values.append(status)
        fields.append("updated_at=?")
        values.append(_now())
        values.append(pending_id)
        with self.tx() as con:
            cur = con.execute(
                f"UPDATE pending_items SET {', '.join(fields)} WHERE pending_id=?",
                values,
            )
            if cur.rowcount == 0:
                raise KeyError(pending_id)

    def pending_counts(self) -> dict[str, int]:
        with self.read() as con:
            rows = con.execute(
                "SELECT status, COUNT(*) c FROM pending_items GROUP BY status"
            ).fetchall()
        return {r["status"]: int(r["c"]) for r in rows}

    # ---------- Stage 14 receipt intelligence / approval center ----------
    def list_pending_reviews(self, *, statuses: tuple[str, ...] = ("PENDING_REVIEW", "NEEDS_REVIEW"),
                             limit: int = 500) -> list[dict[str, Any]]:
        statuses = tuple(str(x) for x in statuses if x)
        if not statuses:
            return []
        placeholders = ",".join("?" for _ in statuses)
        with self.read() as con:
            rows = con.execute(
                f"""SELECT p.*, tm.raw_text, tm.content_type, tm.message_date,
                           tm.private_review_message_id, tm.reaction_state,
                           ra.analysis_id, ra.provider AS receipt_provider,
                           ra.document_type AS receipt_document_type,
                           ra.image_path AS receipt_image_path,
                           ra.ocr_text AS receipt_ocr_text,
                           ra.field_confidences_json, ra.conflicts_json,
                           ra.duplicate_candidates_json
                    FROM pending_items p
                    JOIN telegram_messages tm
                      ON tm.chat_id=p.telegram_chat_id AND tm.message_id=p.telegram_message_id
                    LEFT JOIN receipt_analyses ra ON ra.pending_id=p.pending_id
                    WHERE p.status IN ({placeholders})
                    ORDER BY p.created_at ASC
                    LIMIT ?""",
                (*statuses, max(1, int(limit))),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            try: d["payload"] = json.loads(d.get("payload_json") or "{}")
            except Exception: d["payload"] = {}
            for src, dst, default in (
                ("field_confidences_json", "field_confidences", {}),
                ("conflicts_json", "conflicts", []),
                ("duplicate_candidates_json", "duplicate_candidates", []),
            ):
                try: d[dst] = json.loads(d.get(src) or json.dumps(default))
                except Exception: d[dst] = default
            out.append(d)
        return out

    def upsert_receipt_analysis(self, *, pending_id: str, provider: str,
                                document_type: str = "OTHER", image_path: str | None = None,
                                image_sha256: str | None = None, ocr_text: str = "",
                                raw_ai: dict[str, Any] | None = None,
                                field_confidences: dict[str, Any] | None = None,
                                conflicts: list[dict[str, Any]] | None = None,
                                duplicate_candidates: list[dict[str, Any]] | None = None,
                                status: str = "ANALYZED") -> dict[str, Any]:
        now = _now()
        with self.tx() as con:
            old = con.execute("SELECT analysis_id FROM receipt_analyses WHERE pending_id=?", (pending_id,)).fetchone()
            analysis_id = old["analysis_id"] if old else _id("RAI")
            con.execute(
                """INSERT INTO receipt_analyses(
                       analysis_id,pending_id,provider,document_type,image_path,image_sha256,ocr_text,
                       raw_ai_json,field_confidences_json,conflicts_json,duplicate_candidates_json,status,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(pending_id) DO UPDATE SET
                       provider=excluded.provider,document_type=excluded.document_type,
                       image_path=COALESCE(excluded.image_path,receipt_analyses.image_path),
                       image_sha256=COALESCE(excluded.image_sha256,receipt_analyses.image_sha256),
                       ocr_text=excluded.ocr_text,raw_ai_json=excluded.raw_ai_json,
                       field_confidences_json=excluded.field_confidences_json,
                       conflicts_json=excluded.conflicts_json,
                       duplicate_candidates_json=excluded.duplicate_candidates_json,
                       status=excluded.status,updated_at=excluded.updated_at""",
                (analysis_id,pending_id,str(provider or "UNKNOWN"),str(document_type or "OTHER"),image_path,image_sha256,
                 ocr_text or "",json.dumps(raw_ai or {},ensure_ascii=False),
                 json.dumps(field_confidences or {},ensure_ascii=False),json.dumps(conflicts or [],ensure_ascii=False),
                 json.dumps(duplicate_candidates or [],ensure_ascii=False),status,now,now),
            )
        return self.get_receipt_analysis(pending_id) or {}

    def get_receipt_analysis(self, pending_id: str) -> Optional[dict[str, Any]]:
        with self.read() as con:
            row = con.execute("SELECT * FROM receipt_analyses WHERE pending_id=?", (pending_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        for src, dst, default in (
            ("raw_ai_json", "raw_ai", {}), ("field_confidences_json", "field_confidences", {}),
            ("conflicts_json", "conflicts", []), ("duplicate_candidates_json", "duplicate_candidates", []),
        ):
            try: d[dst] = json.loads(d.get(src) or json.dumps(default))
            except Exception: d[dst] = default
        return d

    def update_receipt_analysis_status(self, pending_id: str, status: str) -> None:
        with self.tx() as con:
            con.execute("UPDATE receipt_analyses SET status=?,updated_at=? WHERE pending_id=?", (status,_now(),pending_id))

    def attach_file_to_pending(self, *, pending_id: str, local_path: str, mime_type: str,
                               document_type: str = "RECEIPT", telegram_file_id: str | None = None,
                               telegram_file_unique_id: str | None = None) -> str:
        item = self.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        aid = _id("ATT")
        with self.tx() as con:
            con.execute(
                """INSERT INTO attachments(attachment_id,entity_type,entity_id,document_type,
                       telegram_file_id,telegram_file_unique_id,telegram_chat_id,telegram_message_id,
                       local_path,mime_type,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (aid,"PENDING",pending_id,document_type,telegram_file_id,telegram_file_unique_id,
                 int(item["telegram_chat_id"]),int(item["telegram_message_id"]),local_path,mime_type,_now()),
            )
        return aid

    def list_pending_attachments(self, pending_id: str) -> list[dict[str, Any]]:
        with self.read() as con:
            rows = con.execute(
                "SELECT * FROM attachments WHERE entity_type='PENDING' AND entity_id=? ORDER BY created_at",
                (pending_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def relink_pending_attachments(self, pending_id: str, *, entity_type: str, entity_id: str) -> int:
        with self.tx() as con:
            cur = con.execute(
                "UPDATE attachments SET entity_type=?,entity_id=? WHERE entity_type='PENDING' AND entity_id=?",
                (entity_type.upper(),entity_id,pending_id),
            )
            return int(cur.rowcount)

    def enqueue_integration_event(self, event_type: str, *, pending_id: str | None = None,
                                  payload: dict[str, Any] | None = None) -> str:
        eid = _id("EVT"); now = _now()
        with self.tx() as con:
            con.execute(
                "INSERT INTO integration_events(event_id,event_type,pending_id,payload_json,status,attempts,created_at,updated_at) VALUES(?,?,?,?, 'PENDING',0,?,?)",
                (eid,event_type,pending_id,json.dumps(payload or {},ensure_ascii=False),now,now),
            )
        return eid

    def get_integration_events(self, *, limit: int = 25) -> list[dict[str, Any]]:
        with self.read() as con:
            rows = con.execute(
                "SELECT * FROM integration_events WHERE status IN ('PENDING','FAILED') ORDER BY created_at LIMIT ?",
                (max(1,int(limit)),),
            ).fetchall()
        out=[]
        for r in rows:
            d=dict(r)
            try:d['payload']=json.loads(d.get('payload_json') or '{}')
            except Exception:d['payload']={}
            out.append(d)
        return out

    def mark_integration_event(self, event_id: str, *, done: bool, error: str | None = None) -> None:
        with self.tx() as con:
            con.execute(
                "UPDATE integration_events SET status=?,attempts=attempts+1,last_error=?,updated_at=? WHERE event_id=?",
                ("DONE" if done else "FAILED",None if done else (error or "unknown")[:2000],_now(),event_id),
            )

    def find_receipt_duplicate_candidates(self, *, amount: int, description: str = "", limit: int = 8) -> list[dict[str, Any]]:
        amount = max(0,int(amount or 0))
        if amount <= 0:
            return []
        with self.read() as con:
            exp = con.execute(
                """SELECT 'EXPENSE' entity_type,expense_id entity_id,shamsi_date event_date,final_amount amount,
                          vendor_name counterparty,description
                   FROM expenses WHERE deleted_at IS NULL AND status<>'CANCELLED' AND final_amount=?
                   ORDER BY updated_at DESC LIMIT ?""", (amount,max(1,int(limit)))
            ).fetchall()
            tx = con.execute(
                """SELECT 'TRANSACTION' entity_type,transaction_id entity_id,shamsi_date event_date,amount,
                          COALESCE(receiver_name,payer_name) counterparty,description
                   FROM transactions WHERE deleted_at IS NULL AND status='POSTED' AND amount=?
                   ORDER BY updated_at DESC LIMIT ?""", (amount,max(1,int(limit)))
            ).fetchall()
        rows=[dict(r) for r in (*exp,*tx)]
        q=(description or '').strip().lower()
        def score(r:dict[str,Any])->int:
            s=60
            d=str(r.get('description') or '').lower()
            if q and (q in d or d in q):s+=25
            return s
        for r in rows:r['match_score']=score(r)
        rows.sort(key=lambda x:int(x.get('match_score') or 0),reverse=True)
        return rows[:max(1,int(limit))]

    def link_pending_to_existing(self, *, pending_id: str, entity_type: str, entity_id: str,
                                 source: str = "GUI", actor_id: str | None = None) -> dict[str, Any]:
        """Resolve a pending document by attaching it to an existing entity.

        This creates NO new financial effect. It is intended for duplicate
        receipts/invoices that document a transaction already present in the ledger.
        """
        typ = str(entity_type or "").upper()
        table_info = {
            "EXPENSE": ("expenses", "expense_id"),
            "TRANSACTION": ("transactions", "transaction_id"),
            "CHEQUE": ("cheques", "cheque_id"),
        }
        if typ not in table_info:
            raise ValueError("فقط اتصال به هزینه، تراکنش یا چک موجود مجاز است.")
        table, key = table_info[typ]
        now = _now()
        with self.tx() as con:
            item = con.execute("SELECT * FROM pending_items WHERE pending_id=?", (pending_id,)).fetchone()
            if not item:
                raise KeyError(pending_id)
            if item["status"] not in {"PENDING_REVIEW", "NEEDS_REVIEW"}:
                raise ValueError("این مورد دیگر در انتظار تأیید نیست.")
            target = con.execute(f"SELECT * FROM {table} WHERE {key}=?", (entity_id,)).fetchone()
            if not target:
                raise KeyError(entity_id)
            con.execute("UPDATE pending_items SET status='APPROVED',updated_at=? WHERE pending_id=?", (now,pending_id))
            con.execute(
                """UPDATE telegram_messages SET state='APPROVED',linked_entity_type=?,linked_entity_id=?,updated_at=?
                   WHERE chat_id=? AND message_id=?""",
                (typ,entity_id,now,int(item["telegram_chat_id"]),int(item["telegram_message_id"])),
            )
            con.execute(
                "UPDATE attachments SET entity_type=?,entity_id=? WHERE entity_type='PENDING' AND entity_id=?",
                (typ,entity_id,pending_id),
            )
            con.execute("UPDATE receipt_analyses SET status='APPROVED',updated_at=? WHERE pending_id=?", (now,pending_id))
            self._audit(con,"pending",pending_id,"LINK_EXISTING",source,
                        before={"status":item["status"]},after={"status":"APPROVED","entity_type":typ,"entity_id":entity_id},actor_id=actor_id)
            event_id = _id("EVT")
            con.execute(
                """INSERT INTO integration_events(event_id,event_type,pending_id,payload_json,status,attempts,created_at,updated_at)
                   VALUES(?,?,?,?,'PENDING',0,?,?)""",
                (event_id,"GUI_APPROVED",pending_id,json.dumps({"linked_existing":True,"entity_type":typ,"entity_id":entity_id},ensure_ascii=False),now,now),
            )
        return {"pending_id":pending_id,"entity_type":typ,"entity_id":entity_id,"event_id":event_id}

    def upsert_learned_rule(self, *, rule_type: str, pattern: str, target_field: str, target_value: str) -> str:
        now=_now()
        with self.tx() as con:
            row=con.execute(
                "SELECT rule_id FROM learned_rules WHERE rule_type=? AND pattern=? AND target_field=? AND target_value=?",
                (rule_type,pattern,target_field,target_value),
            ).fetchone()
            if row:
                rid=row['rule_id'];con.execute("UPDATE learned_rules SET hit_count=hit_count+1,is_active=1,updated_at=? WHERE rule_id=?",(now,rid))
            else:
                rid=_id('RULE');con.execute(
                    "INSERT INTO learned_rules(rule_id,rule_type,pattern,target_field,target_value,hit_count,is_active,created_at,updated_at) VALUES(?,?,?,?,?,1,1,?,?)",
                    (rid,rule_type,pattern,target_field,target_value,now,now),
                )
        return rid

    def apply_learned_rules(self, text: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized=(text or '').replace('ي','ی').replace('ك','ک').lower()
        out=dict(payload)
        with self.read() as con:
            rows=con.execute("SELECT * FROM learned_rules WHERE is_active=1 ORDER BY hit_count DESC,created_at").fetchall()
        for row in rows:
            pat=str(row['pattern'] or '').replace('ي','ی').replace('ك','ک').lower()
            if pat and pat in normalized:
                field=str(row['target_field']);value=row['target_value']
                if not str(out.get(field) or '').strip():out[field]=value
        return out

    # ---------- core writes ----------
    def post_transaction(self, *, event_date: str, direction: str, amount: int, category: str,
                         description: str = "", event_time: Optional[str] = None,
                         shamsi_date: Optional[str] = None, payer_name: Optional[str] = None,
                         receiver_name: Optional[str] = None, source_type: str = "SYSTEM",
                         telegram_chat_id: Optional[int] = None,
                         telegram_message_id: Optional[int] = None,
                         expense_id: Optional[str] = None, sale_id: Optional[str] = None,
                         loan_id: Optional[str] = None, actor_id: Optional[str] = None,
                         transaction_id: Optional[str] = None) -> str:
        direction = direction.upper()
        if direction not in {"IN", "OUT"}:
            raise ValueError("direction must be IN or OUT")
        if amount < 0:
            raise ValueError("amount must be positive; direction carries the sign")
        transaction_id = transaction_id or _id("TX")
        now = _now()
        row = {
            "transaction_id": transaction_id, "event_date": event_date,
            "shamsi_date": shamsi_date, "event_time": event_time, "direction": direction,
            "amount": int(amount), "category": category, "payer_name": payer_name,
            "receiver_name": receiver_name, "description": description,
            "source_type": source_type, "telegram_chat_id": telegram_chat_id,
            "telegram_message_id": telegram_message_id, "expense_id": expense_id,
            "sale_id": sale_id, "loan_id": loan_id, "status": "POSTED",
            "sync_status": "PENDING", "created_at": now, "updated_at": now,
        }
        with self.tx() as con:
            con.execute(
                """INSERT INTO transactions(
                    transaction_id,event_date,shamsi_date,event_time,direction,amount,category,
                    payer_name,receiver_name,description,source_type,telegram_chat_id,
                    telegram_message_id,expense_id,sale_id,loan_id,status,sync_status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                tuple(row[k] for k in [
                    "transaction_id","event_date","shamsi_date","event_time","direction","amount","category",
                    "payer_name","receiver_name","description","source_type","telegram_chat_id","telegram_message_id",
                    "expense_id","sale_id","loan_id","status","sync_status","created_at","updated_at"
                ]),
            )
            self._audit(con, "transaction", transaction_id, "CREATE", source_type, after=row, actor_id=actor_id)
            self._enqueue_sync(con, "transaction", transaction_id, "CREATE", row)
        return transaction_id

    def void_transaction(self, transaction_id: str, *, source: str = "SYSTEM",
                         actor_id: Optional[str] = None, reason: str = "") -> None:
        with self.tx() as con:
            old = con.execute("SELECT * FROM transactions WHERE transaction_id=?", (transaction_id,)).fetchone()
            if not old:
                raise KeyError(transaction_id)
            before = dict(old)
            if old["status"] == "VOIDED":
                return  # idempotent
            con.execute(
                "UPDATE transactions SET status='VOIDED', deleted_at=?, updated_at=?, sync_status='PENDING' WHERE transaction_id=?",
                (_now(), _now(), transaction_id),
            )
            after = dict(con.execute("SELECT * FROM transactions WHERE transaction_id=?", (transaction_id,)).fetchone())
            if reason:
                after["void_reason"] = reason
            self._audit(con, "transaction", transaction_id, "VOID", source, before, after, actor_id)
            self._enqueue_sync(con, "transaction", transaction_id, "DELETE", {"reason": reason})

    def create_expense(self, *, event_date: str, final_amount: int, description: str,
                       invoice_amount: Optional[int] = None, discount_amount: Optional[int] = None,
                       shamsi_date: Optional[str] = None, vendor_name: Optional[str] = None,
                       category: str = "OTHER", construction_stage: Optional[str] = None,
                       manager_fee_eligible: bool = True, status: str = "APPROVED",
                       source: str = "SYSTEM", actor_id: Optional[str] = None,
                       expense_id: Optional[str] = None) -> str:
        if final_amount < 0:
            raise ValueError("final_amount must be >= 0")
        invoice_amount = final_amount if invoice_amount is None else int(invoice_amount)
        if invoice_amount < final_amount and discount_amount is None:
            discount_amount = 0
        discount_amount = max(invoice_amount - final_amount, 0) if discount_amount is None else int(discount_amount)
        expense_id = expense_id or _id("EX")
        now = _now()
        row = {
            "expense_id": expense_id, "event_date": event_date, "shamsi_date": shamsi_date,
            "vendor_name": vendor_name, "description": description, "category": category,
            "construction_stage": construction_stage, "invoice_amount": invoice_amount,
            "final_amount": int(final_amount), "discount_amount": discount_amount,
            "manager_fee_eligible": 1 if manager_fee_eligible else 0, "status": status,
            "created_at": now, "updated_at": now,
        }
        with self.tx() as con:
            con.execute(
                """INSERT INTO expenses(expense_id,event_date,shamsi_date,vendor_name,description,category,
                construction_stage,invoice_amount,final_amount,discount_amount,manager_fee_eligible,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                tuple(row[k] for k in ["expense_id","event_date","shamsi_date","vendor_name","description","category",
                                      "construction_stage","invoice_amount","final_amount","discount_amount",
                                      "manager_fee_eligible","status","created_at","updated_at"]),
            )
            self._audit(con, "expense", expense_id, "CREATE", source, after=row, actor_id=actor_id)
            self._enqueue_sync(con, "expense", expense_id, "CREATE", row)
        return expense_id

    def cancel_expense(self, expense_id: str, *, source: str = "SYSTEM",
                       actor_id: Optional[str] = None, reason: str = "") -> None:
        with self.tx() as con:
            old = con.execute("SELECT * FROM expenses WHERE expense_id=?", (expense_id,)).fetchone()
            if not old:
                raise KeyError(expense_id)
            if old["status"] == "CANCELLED":
                return
            before = dict(old)
            con.execute("UPDATE expenses SET status='CANCELLED', deleted_at=?, updated_at=? WHERE expense_id=?",
                        (_now(), _now(), expense_id))
            after = dict(con.execute("SELECT * FROM expenses WHERE expense_id=?", (expense_id,)).fetchone())
            if reason:
                after["cancel_reason"] = reason
            self._audit(con, "expense", expense_id, "CANCEL", source, before, after, actor_id)
            self._enqueue_sync(con, "expense", expense_id, "DELETE", {"reason": reason})

    def add_payment(self, *, expense_id: str, payment_date: str, amount: int, method: str,
                    transaction_id: Optional[str] = None, cheque_id: Optional[str] = None,
                    payment_date_shamsi: Optional[str] = None, status: str = "COMPLETED",
                    description: str = "", source: str = "SYSTEM",
                    actor_id: Optional[str] = None, payment_id: Optional[str] = None) -> str:
        method = method.upper()
        payment_id = payment_id or _id("PAY")
        now = _now()
        with self.tx() as con:
            if not con.execute("SELECT 1 FROM expenses WHERE expense_id=?", (expense_id,)).fetchone():
                raise KeyError(expense_id)
            row = {
                "payment_id": payment_id, "expense_id": expense_id, "payment_date": payment_date,
                "payment_date_shamsi": payment_date_shamsi, "amount": int(amount), "method": method,
                "transaction_id": transaction_id, "cheque_id": cheque_id, "status": status,
                "description": description, "created_at": now, "updated_at": now,
            }
            con.execute(
                """INSERT INTO payments(payment_id,expense_id,payment_date,payment_date_shamsi,amount,method,
                transaction_id,cheque_id,status,description,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                tuple(row[k] for k in ["payment_id","expense_id","payment_date","payment_date_shamsi","amount","method",
                                      "transaction_id","cheque_id","status","description","created_at","updated_at"]),
            )
            self._audit(con, "payment", payment_id, "CREATE", source, after=row, actor_id=actor_id)
            self._enqueue_sync(con, "payment", payment_id, "CREATE", row)
            self._refresh_expense_payment_status(con, expense_id)
        return payment_id

    def _refresh_expense_payment_status(self, con: sqlite3.Connection, expense_id: str) -> None:
        exp = con.execute("SELECT final_amount,status FROM expenses WHERE expense_id=?", (expense_id,)).fetchone()
        if not exp or exp["status"] == "CANCELLED":
            return
        paid = con.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments WHERE expense_id=? AND status='COMPLETED'",
            (expense_id,),
        ).fetchone()[0]
        if paid <= 0:
            new_status = "APPROVED"
        elif paid < exp["final_amount"]:
            new_status = "PARTIALLY_PAID"
        else:
            new_status = "PAID"
        con.execute("UPDATE expenses SET status=?, updated_at=? WHERE expense_id=?", (new_status, _now(), expense_id))

    def create_cheque(self, *, amount: int, issue_date: str, due_date: str,
                      expense_id: Optional[str] = None, issue_date_shamsi: Optional[str] = None,
                      due_date_shamsi: Optional[str] = None, cheque_serial: Optional[str] = None,
                      issuer_bank: Optional[str] = None, issuer_name: Optional[str] = None,
                      cheque_type: str = "PHYSICAL", receiver_name: Optional[str] = None,
                      description: str = "", source: str = "SYSTEM", actor_id: Optional[str] = None,
                      cheque_id: Optional[str] = None, is_guarantee: bool = False) -> str:
        cheque_id = cheque_id or _id("CHQ")
        now = _now()
        row = {
            "cheque_id": cheque_id, "expense_id": expense_id, "amount": int(amount),
            "issue_date": issue_date, "issue_date_shamsi": issue_date_shamsi,
            "due_date": due_date, "due_date_shamsi": due_date_shamsi,
            "cheque_serial": cheque_serial, "issuer_bank": issuer_bank,
            "issuer_name": issuer_name, "cheque_type": (cheque_type or "PHYSICAL").upper(),
            "receiver_name": receiver_name, "description": description, "status": "ISSUED", "is_guarantee": 1 if is_guarantee else 0,
            "created_at": now, "updated_at": now,
        }
        with self.tx() as con:
            con.execute(
                """INSERT INTO cheques(cheque_id,expense_id,amount,issue_date,issue_date_shamsi,due_date,
                due_date_shamsi,cheque_serial,issuer_bank,issuer_name,cheque_type,receiver_name,description,status,is_guarantee,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                tuple(row[k] for k in ["cheque_id","expense_id","amount","issue_date","issue_date_shamsi","due_date",
                                      "due_date_shamsi","cheque_serial","issuer_bank","issuer_name","cheque_type","receiver_name","description",
                                      "status","is_guarantee","created_at","updated_at"]),
            )
            self._audit(con, "cheque", cheque_id, "CREATE", source, after=row, actor_id=actor_id)
            self._enqueue_sync(con, "cheque", cheque_id, "CREATE", row)
        return cheque_id

    def cash_cheque(self, cheque_id: str, *, cashed_date: str, cashed_date_shamsi: Optional[str] = None,
                    source: str = "SYSTEM", actor_id: Optional[str] = None) -> str:
        with self.tx() as con:
            chq = con.execute("SELECT * FROM cheques WHERE cheque_id=?", (cheque_id,)).fetchone()
            if not chq:
                raise KeyError(cheque_id)
            if chq["status"] == "CASHED" and chq["cash_transaction_id"]:
                return chq["cash_transaction_id"]  # idempotent
            if chq["status"] == "CANCELLED":
                raise ValueError("cancelled cheque cannot be cashed")

            tx_id = _id("TX")
            now = _now()
            con.execute(
                """INSERT INTO transactions(transaction_id,event_date,shamsi_date,direction,amount,category,
                receiver_name,description,source_type,expense_id,status,sync_status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?, 'POSTED','PENDING',?,?)""",
                (
                    tx_id, cashed_date, cashed_date_shamsi, "OUT", chq["amount"], "EXPENSE_PAYMENT_CHEQUE",
                    chq["receiver_name"], chq["description"], source, chq["expense_id"], now, now,
                ),
            )
            con.execute(
                "UPDATE cheques SET status='CASHED', cashed_date=?, cashed_date_shamsi=?, cash_transaction_id=?, updated_at=? WHERE cheque_id=?",
                (cashed_date, cashed_date_shamsi, tx_id, now, cheque_id),
            )
            if chq["expense_id"]:
                payment = con.execute(
                    "SELECT payment_id FROM payments WHERE cheque_id=? AND status!='CANCELLED' LIMIT 1",
                    (cheque_id,),
                ).fetchone()
                if payment:
                    con.execute(
                        "UPDATE payments SET transaction_id=?, status='COMPLETED', updated_at=? WHERE payment_id=?",
                        (tx_id, now, payment["payment_id"]),
                    )
                    payment_row = dict(con.execute("SELECT * FROM payments WHERE payment_id=?", (payment["payment_id"],)).fetchone())
                    self._enqueue_sync(con, "payment", payment["payment_id"], "UPDATE", payment_row)
                    self._refresh_expense_payment_status(con, chq["expense_id"])
                    exp_row = con.execute("SELECT * FROM expenses WHERE expense_id=?", (chq["expense_id"],)).fetchone()
                    if exp_row:
                        self._enqueue_sync(con, "expense", chq["expense_id"], "UPDATE", dict(exp_row))
            con.execute(
                "UPDATE reminders SET status='CANCELLED', updated_at=? "
                "WHERE entity_type='CHEQUE' AND entity_id=? AND status='SCHEDULED'",
                (now, cheque_id),
            )
            tx_row = dict(con.execute("SELECT * FROM transactions WHERE transaction_id=?", (tx_id,)).fetchone())
            cheque_row = dict(con.execute("SELECT * FROM cheques WHERE cheque_id=?", (cheque_id,)).fetchone())
            self._audit(con, "cheque", cheque_id, "CASH", source, before=dict(chq),
                        after=cheque_row, actor_id=actor_id)
            self._audit(con, "transaction", tx_id, "CREATE", source, after=tx_row, actor_id=actor_id)
            self._enqueue_sync(con, "cheque", cheque_id, "UPDATE", cheque_row)
            self._enqueue_sync(con, "transaction", tx_id, "CREATE", tx_row)
            return tx_id

    # ---------- Stage 3 atomic posting ----------
    def get_financial_posting(self, pending_id: str) -> Optional[dict[str, Any]]:
        with self.read() as con:
            row = con.execute(
                "SELECT * FROM financial_postings WHERE pending_id=?",
                (pending_id,),
            ).fetchone()
            if not row:
                return None
            out = dict(row)
            try:
                out["plan"] = json.loads(out.pop("plan_json"))
            except Exception:
                out["plan"] = {}
            return out

    def apply_financial_posting(self, *, pending_id: str, plan: dict[str, Any],
                                source: str = "TELEGRAM", actor_id: Optional[str] = None) -> dict[str, Any]:
        """Atomically post one approved Telegram pending item into the financial ledger.

        This is idempotent by pending_id. A repeated approval returns the original
        posting and never duplicates an Expense/Transaction/Payment/Cheque.
        """
        now = _now()
        posting_id = _id("POST")
        posting_type = str(plan.get("posting_type") or "").upper()
        if posting_type not in {"EXPENSE", "INCOME", "OUTFLOW", "CHEQUE"}:
            raise ValueError(f"unsupported posting_type: {posting_type}")

        with self.tx() as con:
            existing = con.execute(
                "SELECT * FROM financial_postings WHERE pending_id=?",
                (pending_id,),
            ).fetchone()
            if existing:
                return dict(existing)

            item = con.execute("SELECT * FROM pending_items WHERE pending_id=?", (pending_id,)).fetchone()
            if not item:
                raise KeyError(pending_id)
            if item["status"] == "REJECTED":
                raise ValueError("rejected item cannot be posted")

            chat_id = int(item["telegram_chat_id"])
            message_id = int(item["telegram_message_id"])
            event_date = str(plan["event_date"])
            shamsi_date = plan.get("shamsi_date")
            event_time = plan.get("event_time")
            description = str(plan.get("description") or "")
            payer_name = plan.get("payer_name") or None
            receiver_name = plan.get("receiver_name") or None

            expense_id = transaction_id = payment_id = cheque_id = None
            primary_entity_type = primary_entity_id = None

            def insert_transaction(direction: str, amount: int, category: str, *, expense_ref: Optional[str] = None) -> str:
                tx_id = _id("TX")
                row = {
                    "transaction_id": tx_id, "event_date": event_date, "shamsi_date": shamsi_date,
                    "event_time": event_time, "direction": direction, "amount": int(amount),
                    "category": category, "payer_name": payer_name, "receiver_name": receiver_name,
                    "description": description, "source_type": source,
                    "telegram_chat_id": chat_id, "telegram_message_id": message_id,
                    "expense_id": expense_ref, "sale_id": None, "loan_id": None,
                    "status": "POSTED", "sync_status": "PENDING", "created_at": now, "updated_at": now,
                }
                con.execute(
                    """INSERT INTO transactions(transaction_id,event_date,shamsi_date,event_time,direction,amount,category,
                    payer_name,receiver_name,description,source_type,telegram_chat_id,telegram_message_id,expense_id,sale_id,
                    loan_id,status,sync_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    tuple(row[k] for k in ["transaction_id","event_date","shamsi_date","event_time","direction","amount",
                                           "category","payer_name","receiver_name","description","source_type","telegram_chat_id",
                                           "telegram_message_id","expense_id","sale_id","loan_id","status","sync_status","created_at","updated_at"]),
                )
                self._audit(con, "transaction", tx_id, "CREATE", source, after=row, actor_id=actor_id)
                self._enqueue_sync(con, "transaction", tx_id, "CREATE", row)
                return tx_id

            if posting_type == "EXPENSE":
                final_amount = int(plan.get("final_amount") or 0)
                if final_amount <= 0:
                    raise ValueError("expense final_amount must be > 0")
                invoice_amount = int(plan.get("invoice_amount") or final_amount)
                if invoice_amount <= 0:
                    invoice_amount = final_amount
                discount_amount = int(plan.get("discount_amount") or max(invoice_amount - final_amount, 0))
                expense_id = _id("EX")
                exp = {
                    "expense_id": expense_id, "event_date": event_date, "shamsi_date": shamsi_date,
                    "vendor_name": receiver_name, "description": description,
                    "category": str(plan.get("expense_category") or "OTHER"),
                    "construction_stage": plan.get("construction_stage") or None,
                    "invoice_amount": invoice_amount, "final_amount": final_amount,
                    "discount_amount": max(discount_amount, 0),
                    "manager_fee_eligible": 1 if plan.get("manager_fee_eligible", True) else 0,
                    "status": "APPROVED", "created_at": now, "updated_at": now,
                }
                con.execute(
                    """INSERT INTO expenses(expense_id,event_date,shamsi_date,vendor_name,description,category,
                    construction_stage,invoice_amount,final_amount,discount_amount,manager_fee_eligible,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    tuple(exp[k] for k in ["expense_id","event_date","shamsi_date","vendor_name","description","category",
                                           "construction_stage","invoice_amount","final_amount","discount_amount",
                                           "manager_fee_eligible","status","created_at","updated_at"]),
                )
                self._audit(con, "expense", expense_id, "CREATE", source, after=exp, actor_id=actor_id)
                self._enqueue_sync(con, "expense", expense_id, "CREATE", exp)

                payment_state = str(plan.get("payment_state") or "UNPAID").upper()
                paid_amount = int(plan.get("paid_amount") or 0)
                method = str(plan.get("payment_method") or "OTHER").upper()
                if method == "UNKNOWN":
                    method = "OTHER"

                if method == "CHEQUE" or bool(plan.get("is_cheque")):
                    due_date = str(plan.get("due_date") or "")
                    if not due_date:
                        raise ValueError("cheque due_date is required")
                    cheque_id = _id("CHQ")
                    cheque_amount = int(plan.get("cheque_amount") or paid_amount or final_amount)
                    chq = {
                        "cheque_id": cheque_id, "expense_id": expense_id, "amount": cheque_amount,
                        "issue_date": str(plan.get("issue_date") or event_date), "issue_date_shamsi": plan.get("issue_date_shamsi") or shamsi_date,
                        "due_date": due_date, "due_date_shamsi": plan.get("due_date_shamsi"),
                        "cheque_serial": plan.get("cheque_serial") or None,
                        "issuer_bank": plan.get("issuer_bank") or None,
                        "receiver_name": receiver_name, "description": description,
                        "status": "ISSUED", "created_at": now, "updated_at": now,
                    }
                    con.execute(
                        """INSERT INTO cheques(cheque_id,expense_id,amount,issue_date,issue_date_shamsi,due_date,due_date_shamsi,
                        cheque_serial,issuer_bank,receiver_name,description,status,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        tuple(chq[k] for k in ["cheque_id","expense_id","amount","issue_date","issue_date_shamsi","due_date",
                                               "due_date_shamsi","cheque_serial","issuer_bank","receiver_name","description",
                                               "status","created_at","updated_at"]),
                    )
                    self._audit(con, "cheque", cheque_id, "CREATE", source, after=chq, actor_id=actor_id)
                    self._enqueue_sync(con, "cheque", cheque_id, "CREATE", chq)

                    payment_id = _id("PAY")
                    pay = {
                        "payment_id": payment_id, "expense_id": expense_id, "payment_date": event_date,
                        "payment_date_shamsi": shamsi_date, "amount": cheque_amount, "method": "CHEQUE",
                        "transaction_id": None, "cheque_id": cheque_id, "status": "PENDING",
                        "description": description, "created_at": now, "updated_at": now,
                    }
                    con.execute(
                        """INSERT INTO payments(payment_id,expense_id,payment_date,payment_date_shamsi,amount,method,
                        transaction_id,cheque_id,status,description,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        tuple(pay[k] for k in ["payment_id","expense_id","payment_date","payment_date_shamsi","amount","method",
                                               "transaction_id","cheque_id","status","description","created_at","updated_at"]),
                    )
                    self._audit(con, "payment", payment_id, "CREATE", source, after=pay, actor_id=actor_id)
                    self._enqueue_sync(con, "payment", payment_id, "CREATE", pay)
                elif payment_state in {"PAID", "PARTIAL"} and paid_amount > 0:
                    transaction_id = insert_transaction(
                        "OUT", paid_amount, "CONSTRUCTION_PAYMENT", expense_ref=expense_id
                    )
                    payment_id = _id("PAY")
                    pay = {
                        "payment_id": payment_id, "expense_id": expense_id, "payment_date": event_date,
                        "payment_date_shamsi": shamsi_date, "amount": paid_amount, "method": method,
                        "transaction_id": transaction_id, "cheque_id": None, "status": "COMPLETED",
                        "description": description, "created_at": now, "updated_at": now,
                    }
                    con.execute(
                        """INSERT INTO payments(payment_id,expense_id,payment_date,payment_date_shamsi,amount,method,
                        transaction_id,cheque_id,status,description,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        tuple(pay[k] for k in ["payment_id","expense_id","payment_date","payment_date_shamsi","amount","method",
                                               "transaction_id","cheque_id","status","description","created_at","updated_at"]),
                    )
                    self._audit(con, "payment", payment_id, "CREATE", source, after=pay, actor_id=actor_id)
                    self._enqueue_sync(con, "payment", payment_id, "CREATE", pay)
                    new_status = "PAID" if paid_amount >= final_amount else "PARTIALLY_PAID"
                    con.execute("UPDATE expenses SET status=?, updated_at=? WHERE expense_id=?", (new_status, now, expense_id))

                primary_entity_type, primary_entity_id = "expense", expense_id

            elif posting_type in {"INCOME", "OUTFLOW"}:
                amount = int(plan.get("amount") or 0)
                if amount <= 0:
                    raise ValueError("transaction amount must be > 0")
                if posting_type == "INCOME":
                    direction = "IN"
                    category = str(plan.get("transaction_category") or "GENERAL_INCOME")
                else:
                    direction = "OUT"
                    category = str(plan.get("transaction_category") or "NON_CONSTRUCTION_OUTFLOW")
                transaction_id = insert_transaction(direction, amount, category)
                primary_entity_type, primary_entity_id = "transaction", transaction_id

            elif posting_type == "CHEQUE":
                amount = int(plan.get("amount") or 0)
                due_date = str(plan.get("due_date") or "")
                if amount <= 0:
                    raise ValueError("cheque amount must be > 0")
                if not due_date:
                    raise ValueError("cheque due_date is required")
                cheque_id = _id("CHQ")
                chq = {
                    "cheque_id": cheque_id, "expense_id": None, "amount": amount,
                    "issue_date": str(plan.get("issue_date") or event_date), "issue_date_shamsi": plan.get("issue_date_shamsi") or shamsi_date,
                    "due_date": due_date, "due_date_shamsi": plan.get("due_date_shamsi"),
                    "cheque_serial": plan.get("cheque_serial") or None,
                    "issuer_bank": plan.get("issuer_bank") or None,
                    "receiver_name": receiver_name, "description": description,
                    "status": "ISSUED", "created_at": now, "updated_at": now,
                }
                con.execute(
                    """INSERT INTO cheques(cheque_id,expense_id,amount,issue_date,issue_date_shamsi,due_date,due_date_shamsi,
                    cheque_serial,issuer_bank,receiver_name,description,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    tuple(chq[k] for k in ["cheque_id","expense_id","amount","issue_date","issue_date_shamsi","due_date",
                                           "due_date_shamsi","cheque_serial","issuer_bank","receiver_name","description",
                                           "status","created_at","updated_at"]),
                )
                self._audit(con, "cheque", cheque_id, "CREATE", source, after=chq, actor_id=actor_id)
                self._enqueue_sync(con, "cheque", cheque_id, "CREATE", chq)
                primary_entity_type, primary_entity_id = "cheque", cheque_id

            if cheque_id:
                cols={r[1] for r in con.execute("PRAGMA table_info(cheques)").fetchall()}
                if 'registration_state' in cols:
                    con.execute("UPDATE cheques SET issuer_name=?, cheque_type=?, registration_state=?, updated_at=? WHERE cheque_id=?",
                                (str(plan.get('issuer_name') or '').strip() or None,
                                 str(plan.get('cheque_type') or 'PHYSICAL').upper(),
                                 str(plan.get('cheque_registration_state') or 'UNKNOWN').upper(), now, cheque_id))
                else:
                    con.execute("UPDATE cheques SET issuer_name=?, cheque_type=?, updated_at=? WHERE cheque_id=?",
                                (str(plan.get('issuer_name') or '').strip() or None,
                                 str(plan.get('cheque_type') or 'PHYSICAL').upper(), now, cheque_id))

            post = {
                "posting_id": posting_id, "pending_id": pending_id, "posting_type": posting_type,
                "primary_entity_type": primary_entity_type, "primary_entity_id": primary_entity_id,
                "expense_id": expense_id, "transaction_id": transaction_id,
                "payment_id": payment_id, "cheque_id": cheque_id,
                "plan_json": json.dumps(plan, ensure_ascii=False), "created_at": now,
            }
            con.execute(
                """INSERT INTO financial_postings(posting_id,pending_id,posting_type,primary_entity_type,primary_entity_id,
                expense_id,transaction_id,payment_id,cheque_id,plan_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                tuple(post[k] for k in ["posting_id","pending_id","posting_type","primary_entity_type","primary_entity_id",
                                        "expense_id","transaction_id","payment_id","cheque_id","plan_json","created_at"]),
            )
            con.execute(
                "UPDATE financial_postings SET status='ACTIVE', updated_at=? WHERE posting_id=?",
                (now, posting_id),
            )
            con.execute("UPDATE pending_items SET status='APPROVED', updated_at=? WHERE pending_id=?", (now, pending_id))
            con.execute(
                """UPDATE telegram_messages SET state='APPROVED', linked_entity_type=?, linked_entity_id=?, updated_at=?
                WHERE chat_id=? AND message_id=?""",
                (primary_entity_type, primary_entity_id, now, chat_id, message_id),
            )
            self._audit(con, "posting", posting_id, "CREATE", source, after=post, actor_id=actor_id)
            return post


    # ---------- Stage 5 revisions / soft delete ----------
    def financial_posting_counts(self) -> dict[str, int]:
        with self.read() as con:
            rows = con.execute(
                "SELECT COALESCE(status,'ACTIVE') status, COUNT(*) c FROM financial_postings GROUP BY COALESCE(status,'ACTIVE')"
            ).fetchall()
        return {str(r["status"]): int(r["c"]) for r in rows}

    def repair_paid_expense_invariants(self, *, source: str = "LEDGER_REPAIR",
                                       actor_id: Optional[str] = None) -> dict[str, Any]:
        """Repair only strict, mechanically-provable PAID expense inconsistencies.

        Scope is intentionally narrow: an ACTIVE EXPENSE posting whose stored plan says
        payment_state=PAID, is not a cheque, and already has a linked COMPLETED payment
        and POSTED cash transaction. In that state, Payment and Transaction must equal
        the realized expense final_amount. This repairs stale paid_amount values left by
        older edit logic without touching legitimate PARTIAL/UNPAID cases.
        """
        now = _now()
        repaired: list[dict[str, Any]] = []
        skipped = 0
        with self.tx() as con:
            rows = con.execute(
                """SELECT * FROM financial_postings
                   WHERE COALESCE(status,'ACTIVE')='ACTIVE' AND posting_type='EXPENSE'"""
            ).fetchall()
            for post in rows:
                try:
                    plan = json.loads(post["plan_json"] or "{}")
                except Exception:
                    skipped += 1
                    continue
                if str(plan.get("payment_state") or "").upper() != "PAID":
                    continue
                if bool(plan.get("is_cheque")) or str(plan.get("payment_method") or "").upper() == "CHEQUE":
                    continue
                expense_id = post["expense_id"]
                payment_id = post["payment_id"]
                transaction_id = post["transaction_id"]
                if not (expense_id and payment_id and transaction_id):
                    skipped += 1
                    continue
                exp = con.execute("SELECT * FROM expenses WHERE expense_id=?", (expense_id,)).fetchone()
                pay = con.execute("SELECT * FROM payments WHERE payment_id=?", (payment_id,)).fetchone()
                tx = con.execute("SELECT * FROM transactions WHERE transaction_id=?", (transaction_id,)).fetchone()
                if not (exp and pay and tx):
                    skipped += 1
                    continue
                if str(pay["status"] or "").upper() != "COMPLETED" or str(tx["status"] or "").upper() != "POSTED":
                    continue
                final_amount = int(exp["final_amount"] or 0)
                if final_amount <= 0:
                    skipped += 1
                    continue

                before_exp, before_pay, before_tx = dict(exp), dict(pay), dict(tx)
                old_plan = dict(plan)
                needs = (
                    int(pay["amount"] or 0) != final_amount
                    or int(tx["amount"] or 0) != final_amount
                    or str(exp["status"] or "").upper() != "PAID"
                    or int(plan.get("paid_amount") or 0) != final_amount
                )
                if not needs:
                    continue

                con.execute(
                    "UPDATE payments SET amount=?, status='COMPLETED', updated_at=? WHERE payment_id=?",
                    (final_amount, now, payment_id),
                )
                con.execute(
                    """UPDATE transactions SET amount=?, status='POSTED', deleted_at=NULL,
                       sync_status='PENDING', updated_at=? WHERE transaction_id=?""",
                    (final_amount, now, transaction_id),
                )
                con.execute(
                    "UPDATE expenses SET status='PAID', deleted_at=NULL, updated_at=? WHERE expense_id=?",
                    (now, expense_id),
                )
                plan["paid_amount"] = final_amount
                plan["payment_state"] = "PAID"
                con.execute(
                    "UPDATE financial_postings SET plan_json=?, updated_at=? WHERE posting_id=?",
                    (json.dumps(plan, ensure_ascii=False), now, post["posting_id"]),
                )

                pending = con.execute("SELECT payload_json FROM pending_items WHERE pending_id=?", (post["pending_id"],)).fetchone()
                if pending:
                    try:
                        payload = json.loads(pending["payload_json"] or "{}")
                    except Exception:
                        payload = {}
                    payload["paid_amount"] = final_amount
                    payload["payment_state"] = "PAID"
                    con.execute(
                        "UPDATE pending_items SET payload_json=?, status='APPROVED', updated_at=? WHERE pending_id=?",
                        (json.dumps(payload, ensure_ascii=False), now, post["pending_id"]),
                    )

                after_exp = self._row_dict(con, "expenses", "expense_id", expense_id)
                after_pay = self._row_dict(con, "payments", "payment_id", payment_id)
                after_tx = self._row_dict(con, "transactions", "transaction_id", transaction_id)
                self._audit(con, "expense", expense_id, "REPAIR_PAID", source, before_exp, after_exp, actor_id)
                self._audit(con, "payment", payment_id, "REPAIR_PAID", source, before_pay, after_pay, actor_id)
                self._audit(con, "transaction", transaction_id, "REPAIR_PAID", source, before_tx, after_tx, actor_id)
                self._audit(con, "posting", post["posting_id"], "REPAIR_PAID", source, old_plan, plan, actor_id)
                self._enqueue_sync(con, "expense", expense_id, "UPDATE", after_exp)
                self._enqueue_sync(con, "payment", payment_id, "UPDATE", after_pay)
                self._enqueue_sync(con, "transaction", transaction_id, "UPDATE", after_tx)
                repaired.append({
                    "posting_id": post["posting_id"],
                    "expense_id": expense_id,
                    "payment_id": payment_id,
                    "transaction_id": transaction_id,
                    "amount": final_amount,
                })
        return {"repaired_count": len(repaired), "skipped": skipped, "repaired": repaired}

    def get_open_revision(self, pending_id: str) -> Optional[dict[str, Any]]:
        with self.read() as con:
            row = con.execute(
                "SELECT * FROM posting_revisions WHERE pending_id=? AND status='PENDING' ORDER BY created_at DESC LIMIT 1",
                (pending_id,),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["old_payload"] = json.loads(out.pop("old_payload_json"))
        out["new_payload"] = json.loads(out.pop("new_payload_json"))
        return out

    def begin_posting_revision(self, *, pending_id: str, new_payload: dict[str, Any],
                               source: str = "PRIVATE_EDIT", actor_id: Optional[str] = None) -> dict[str, Any]:
        """Start/update one pending revision while preserving the last approved payload.

        The approved ledger remains untouched until revise_financial_posting() is called.
        Repeated Telegram edits update the same open revision instead of stacking revisions.
        """
        now = _now()
        with self.tx() as con:
            post = con.execute(
                "SELECT * FROM financial_postings WHERE pending_id=?",
                (pending_id,),
            ).fetchone()
            if not post:
                raise KeyError(pending_id)
            if str(post["status"] or "ACTIVE") != "ACTIVE":
                raise ValueError("ثبت حذف‌شده قابل ویرایش نیست.")
            item = con.execute("SELECT * FROM pending_items WHERE pending_id=?", (pending_id,)).fetchone()
            if not item:
                raise KeyError(pending_id)

            existing = con.execute(
                "SELECT * FROM posting_revisions WHERE pending_id=? AND status='PENDING' ORDER BY created_at DESC LIMIT 1",
                (pending_id,),
            ).fetchone()
            if existing:
                revision_id = existing["revision_id"]
                old_payload_json = existing["old_payload_json"]
                con.execute(
                    "UPDATE posting_revisions SET new_payload_json=?, source=?, updated_at=? WHERE revision_id=?",
                    (json.dumps(new_payload, ensure_ascii=False), source, now, revision_id),
                )
            else:
                revision_id = _id("REV")
                old_payload_json = item["payload_json"]
                con.execute(
                    """INSERT INTO posting_revisions(
                        revision_id,pending_id,old_payload_json,new_payload_json,status,source,created_at,updated_at
                    ) VALUES(?,?,?,?, 'PENDING', ?, ?, ?)""",
                    (revision_id, pending_id, old_payload_json, json.dumps(new_payload, ensure_ascii=False), source, now, now),
                )

            detected = str(new_payload.get("detected_type") or item["detected_type"] or "UNKNOWN")
            confidence = new_payload.get("confidence")
            con.execute(
                """UPDATE pending_items SET payload_json=?, detected_type=?, confidence=?, status='EDIT_PENDING', updated_at=?
                WHERE pending_id=?""",
                (json.dumps(new_payload, ensure_ascii=False), detected,
                 float(confidence) if confidence is not None else item["confidence"], now, pending_id),
            )
            con.execute(
                """UPDATE telegram_messages SET state='EDIT_PENDING', reaction_state='NONE', updated_at=?
                WHERE chat_id=? AND message_id=?""",
                (now, int(item["telegram_chat_id"]), int(item["telegram_message_id"])),
            )
            self._audit(
                con, "posting_revision", revision_id, "BEGIN", source,
                before=json.loads(old_payload_json), after=new_payload, actor_id=actor_id,
            )
            row = con.execute("SELECT * FROM posting_revisions WHERE revision_id=?", (revision_id,)).fetchone()
        out = dict(row)
        out["old_payload"] = json.loads(out.pop("old_payload_json"))
        out["new_payload"] = json.loads(out.pop("new_payload_json"))
        return out

    def reject_posting_revision(self, *, pending_id: str, source: str = "PRIVATE_EDIT",
                                actor_id: Optional[str] = None) -> dict[str, Any]:
        now = _now()
        with self.tx() as con:
            rev = con.execute(
                "SELECT * FROM posting_revisions WHERE pending_id=? AND status='PENDING' ORDER BY created_at DESC LIMIT 1",
                (pending_id,),
            ).fetchone()
            if not rev:
                raise ValueError("ویرایش در انتظار تأییدی وجود ندارد.")
            item = con.execute("SELECT * FROM pending_items WHERE pending_id=?", (pending_id,)).fetchone()
            if not item:
                raise KeyError(pending_id)
            old_payload = json.loads(rev["old_payload_json"])
            old_type = str(old_payload.get("detected_type") or item["detected_type"] or "UNKNOWN")
            old_conf = old_payload.get("confidence")
            con.execute(
                "UPDATE posting_revisions SET status='REJECTED', updated_at=? WHERE revision_id=?",
                (now, rev["revision_id"]),
            )
            con.execute(
                """UPDATE pending_items SET payload_json=?, detected_type=?, confidence=?, status='APPROVED', updated_at=?
                WHERE pending_id=?""",
                (rev["old_payload_json"], old_type,
                 float(old_conf) if old_conf is not None else item["confidence"], now, pending_id),
            )
            con.execute(
                """UPDATE telegram_messages SET state='APPROVED', updated_at=?
                WHERE chat_id=? AND message_id=?""",
                (now, int(item["telegram_chat_id"]), int(item["telegram_message_id"])),
            )
            self._audit(
                con, "posting_revision", rev["revision_id"], "REJECT", source,
                before=json.loads(rev["new_payload_json"]), after=old_payload, actor_id=actor_id,
            )
            return old_payload

    @staticmethod
    def _row_dict(con: sqlite3.Connection, table: str, pk: str, entity_id: str) -> dict[str, Any]:
        row = con.execute(f"SELECT * FROM {table} WHERE {pk}=?", (entity_id,)).fetchone()
        return dict(row) if row else {}

    def revise_financial_posting(self, *, pending_id: str, plan: dict[str, Any],
                                 source: str = "TELEGRAM_EDIT", actor_id: Optional[str] = None) -> dict[str, Any]:
        """Apply an approved edit to the existing posting without creating a duplicate posting.

        Stage 5 keeps the posting_id and all compatible component IDs stable. Changing
        the high-level accounting type (e.g. EXPENSE -> INCOME) is intentionally blocked;
        that requires delete + new entry so the audit trail remains unambiguous.
        """
        now = _now()
        new_type = str(plan.get("posting_type") or "").upper()
        with self.tx() as con:
            post = con.execute("SELECT * FROM financial_postings WHERE pending_id=?", (pending_id,)).fetchone()
            if not post:
                raise KeyError(pending_id)
            if str(post["status"] or "ACTIVE") != "ACTIVE":
                raise ValueError("ثبت حذف‌شده قابل اصلاح نیست.")
            old_type = str(post["posting_type"] or "").upper()
            if new_type != old_type:
                raise ValueError("نوع اصلی ثبت بعد از ثبت قطعی قابل تغییر نیست؛ ابتدا ثبت را حذف و مورد جدید ایجاد کنید.")
            item = con.execute("SELECT * FROM pending_items WHERE pending_id=?", (pending_id,)).fetchone()
            if not item:
                raise KeyError(pending_id)
            revision = con.execute(
                "SELECT * FROM posting_revisions WHERE pending_id=? AND status='PENDING' ORDER BY created_at DESC LIMIT 1",
                (pending_id,),
            ).fetchone()
            if not revision:
                raise ValueError("ویرایش در انتظار تأییدی وجود ندارد.")

            event_date = str(plan["event_date"])
            shamsi_date = plan.get("shamsi_date")
            event_time = plan.get("event_time")
            description = str(plan.get("description") or "")
            payer_name = plan.get("payer_name") or None
            receiver_name = plan.get("receiver_name") or None

            expense_id = post["expense_id"]
            transaction_id = post["transaction_id"]
            payment_id = post["payment_id"]
            cheque_id = post["cheque_id"]

            def sync_update(entity_type: str, entity_id: Optional[str], before: dict[str, Any],
                            action: str = "UPDATE") -> dict[str, Any]:
                if not entity_id:
                    return {}
                table_pk = {
                    "transaction": ("transactions", "transaction_id"),
                    "expense": ("expenses", "expense_id"),
                    "payment": ("payments", "payment_id"),
                    "cheque": ("cheques", "cheque_id"),
                }[entity_type]
                after = self._row_dict(con, table_pk[0], table_pk[1], entity_id)
                self._audit(con, entity_type, entity_id, action, source, before, after, actor_id)
                self._enqueue_sync(con, entity_type, entity_id, "UPDATE", after)
                return after

            if old_type == "EXPENSE":
                if not expense_id:
                    raise ValueError("Expense لینک‌شده پیدا نشد.")
                old_exp = self._row_dict(con, "expenses", "expense_id", expense_id)
                if not old_exp:
                    raise KeyError(expense_id)

                if cheque_id:
                    current_cheque = self._row_dict(con, "cheques", "cheque_id", cheque_id)
                    if current_cheque and current_cheque.get("status") == "CASHED":
                        raise ValueError("چک پاس‌شده را نمی‌توان با Edit ساده اصلاح کرد؛ برای آن سند اصلاحی/برگشت وجه لازم است.")

                final_amount = int(plan.get("final_amount") or 0)
                if final_amount <= 0:
                    raise ValueError("expense final_amount must be > 0")
                invoice_amount = int(plan.get("invoice_amount") or final_amount)
                if invoice_amount <= 0:
                    invoice_amount = final_amount
                discount_amount = int(plan.get("discount_amount") or max(invoice_amount - final_amount, 0))
                method = str(plan.get("payment_method") or "OTHER").upper()
                if method == "UNKNOWN":
                    method = "OTHER"
                payment_state = str(plan.get("payment_state") or "UNPAID").upper()
                paid_amount = int(plan.get("paid_amount") or 0)
                new_is_cheque = method == "CHEQUE" or bool(plan.get("is_cheque"))

                # Update the realized expense itself first. Payment-state is finalized below.
                con.execute(
                    """UPDATE expenses SET event_date=?, shamsi_date=?, vendor_name=?, description=?, category=?,
                    construction_stage=?, invoice_amount=?, final_amount=?, discount_amount=?, manager_fee_eligible=?,
                    status='APPROVED', deleted_at=NULL, updated_at=? WHERE expense_id=?""",
                    (event_date, shamsi_date, receiver_name, description,
                     str(plan.get("expense_category") or "OTHER"), plan.get("construction_stage") or None,
                     invoice_amount, final_amount, max(discount_amount, 0),
                     1 if plan.get("manager_fee_eligible", True) else 0, now, expense_id),
                )
                sync_update("expense", expense_id, old_exp)

                # Existing component snapshots, if any.
                old_tx = self._row_dict(con, "transactions", "transaction_id", transaction_id) if transaction_id else {}
                old_pay = self._row_dict(con, "payments", "payment_id", payment_id) if payment_id else {}
                old_chq = self._row_dict(con, "cheques", "cheque_id", cheque_id) if cheque_id else {}

                if new_is_cheque:
                    due_date = str(plan.get("due_date") or "")
                    if not due_date:
                        raise ValueError("سررسید چک مشخص نیست.")
                    cheque_amount = int(plan.get("cheque_amount") or final_amount)
                    if transaction_id and old_tx:
                        con.execute(
                            "UPDATE transactions SET status='VOIDED', deleted_at=?, sync_status='PENDING', updated_at=? WHERE transaction_id=?",
                            (now, now, transaction_id),
                        )
                        sync_update("transaction", transaction_id, old_tx, "VOID")
                    if not cheque_id:
                        cheque_id = _id("CHQ")
                        con.execute(
                            """INSERT INTO cheques(cheque_id,expense_id,amount,issue_date,issue_date_shamsi,due_date,due_date_shamsi,
                            cheque_serial,issuer_bank,receiver_name,description,status,created_at,updated_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (cheque_id, expense_id, cheque_amount, event_date, shamsi_date, due_date,
                             plan.get("due_date_shamsi"), plan.get("cheque_serial") or None,
                             plan.get("issuer_bank") or None, receiver_name, description, "ISSUED", now, now),
                        )
                        new_chq = self._row_dict(con, "cheques", "cheque_id", cheque_id)
                        self._audit(con, "cheque", cheque_id, "CREATE", source, after=new_chq, actor_id=actor_id)
                        self._enqueue_sync(con, "cheque", cheque_id, "CREATE", new_chq)
                    else:
                        con.execute(
                            """UPDATE cheques SET expense_id=?, amount=?, issue_date=?, issue_date_shamsi=?, due_date=?, due_date_shamsi=?,
                            cashed_date=NULL, cashed_date_shamsi=NULL, cheque_serial=?, issuer_bank=?, receiver_name=?, description=?,
                            status='ISSUED', cash_transaction_id=NULL, updated_at=? WHERE cheque_id=?""",
                            (expense_id, cheque_amount, event_date, shamsi_date, due_date, plan.get("due_date_shamsi"),
                             plan.get("cheque_serial") or None, plan.get("issuer_bank") or None, receiver_name,
                             description, now, cheque_id),
                        )
                        sync_update("cheque", cheque_id, old_chq)

                    if not payment_id:
                        payment_id = _id("PAY")
                        con.execute(
                            """INSERT INTO payments(payment_id,expense_id,payment_date,payment_date_shamsi,amount,method,
                            transaction_id,cheque_id,status,description,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (payment_id, expense_id, event_date, shamsi_date, cheque_amount, "CHEQUE", None,
                             cheque_id, "PENDING", description, now, now),
                        )
                        new_pay = self._row_dict(con, "payments", "payment_id", payment_id)
                        self._audit(con, "payment", payment_id, "CREATE", source, after=new_pay, actor_id=actor_id)
                        self._enqueue_sync(con, "payment", payment_id, "CREATE", new_pay)
                    else:
                        con.execute(
                            """UPDATE payments SET expense_id=?, payment_date=?, payment_date_shamsi=?, amount=?, method='CHEQUE',
                            transaction_id=NULL, cheque_id=?, status='PENDING', description=?, updated_at=? WHERE payment_id=?""",
                            (expense_id, event_date, shamsi_date, cheque_amount, cheque_id, description, now, payment_id),
                        )
                        sync_update("payment", payment_id, old_pay)
                    con.execute("UPDATE expenses SET status='APPROVED', updated_at=? WHERE expense_id=?", (now, expense_id))

                elif payment_state in {"PAID", "PARTIAL"} and paid_amount > 0:
                    if cheque_id and old_chq:
                        con.execute("UPDATE cheques SET status='CANCELLED', updated_at=? WHERE cheque_id=?", (now, cheque_id))
                        sync_update("cheque", cheque_id, old_chq, "CANCEL")
                    if not transaction_id:
                        transaction_id = _id("TX")
                        con.execute(
                            """INSERT INTO transactions(transaction_id,event_date,shamsi_date,event_time,direction,amount,category,
                            payer_name,receiver_name,description,source_type,telegram_chat_id,telegram_message_id,expense_id,status,
                            sync_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'POSTED','PENDING',?,?)""",
                            (transaction_id, event_date, shamsi_date, event_time, "OUT", paid_amount,
                             "CONSTRUCTION_PAYMENT", payer_name, receiver_name, description, source,
                             int(item["telegram_chat_id"]), int(item["telegram_message_id"]), expense_id, now, now),
                        )
                        new_tx = self._row_dict(con, "transactions", "transaction_id", transaction_id)
                        self._audit(con, "transaction", transaction_id, "CREATE", source, after=new_tx, actor_id=actor_id)
                        self._enqueue_sync(con, "transaction", transaction_id, "CREATE", new_tx)
                    else:
                        con.execute(
                            """UPDATE transactions SET event_date=?, shamsi_date=?, event_time=?, direction='OUT', amount=?,
                            category='CONSTRUCTION_PAYMENT', payer_name=?, receiver_name=?, description=?, source_type=?,
                            expense_id=?, status='POSTED', deleted_at=NULL, sync_status='PENDING', updated_at=? WHERE transaction_id=?""",
                            (event_date, shamsi_date, event_time, paid_amount, payer_name, receiver_name, description,
                             source, expense_id, now, transaction_id),
                        )
                        sync_update("transaction", transaction_id, old_tx)

                    if not payment_id:
                        payment_id = _id("PAY")
                        con.execute(
                            """INSERT INTO payments(payment_id,expense_id,payment_date,payment_date_shamsi,amount,method,
                            transaction_id,cheque_id,status,description,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (payment_id, expense_id, event_date, shamsi_date, paid_amount, method,
                             transaction_id, None, "COMPLETED", description, now, now),
                        )
                        new_pay = self._row_dict(con, "payments", "payment_id", payment_id)
                        self._audit(con, "payment", payment_id, "CREATE", source, after=new_pay, actor_id=actor_id)
                        self._enqueue_sync(con, "payment", payment_id, "CREATE", new_pay)
                    else:
                        con.execute(
                            """UPDATE payments SET expense_id=?, payment_date=?, payment_date_shamsi=?, amount=?, method=?,
                            transaction_id=?, cheque_id=NULL, status='COMPLETED', description=?, updated_at=? WHERE payment_id=?""",
                            (expense_id, event_date, shamsi_date, paid_amount, method, transaction_id, description, now, payment_id),
                        )
                        sync_update("payment", payment_id, old_pay)
                    exp_status = "PAID" if paid_amount >= final_amount else "PARTIALLY_PAID"
                    con.execute("UPDATE expenses SET status=?, updated_at=? WHERE expense_id=?", (exp_status, now, expense_id))
                else:
                    if transaction_id and old_tx:
                        con.execute(
                            "UPDATE transactions SET status='VOIDED', deleted_at=?, sync_status='PENDING', updated_at=? WHERE transaction_id=?",
                            (now, now, transaction_id),
                        )
                        sync_update("transaction", transaction_id, old_tx, "VOID")
                    if cheque_id and old_chq:
                        con.execute("UPDATE cheques SET status='CANCELLED', updated_at=? WHERE cheque_id=?", (now, cheque_id))
                        sync_update("cheque", cheque_id, old_chq, "CANCEL")
                    if payment_id and old_pay:
                        con.execute("UPDATE payments SET status='CANCELLED', updated_at=? WHERE payment_id=?", (now, payment_id))
                        sync_update("payment", payment_id, old_pay, "CANCEL")
                    con.execute("UPDATE expenses SET status='APPROVED', updated_at=? WHERE expense_id=?", (now, expense_id))

                # Final expense row changed again when payment status was finalized.
                self._enqueue_sync(con, "expense", expense_id, "UPDATE", self._row_dict(con, "expenses", "expense_id", expense_id))

            elif old_type in {"INCOME", "OUTFLOW"}:
                if not transaction_id:
                    raise ValueError("Transaction لینک‌شده پیدا نشد.")
                old_tx = self._row_dict(con, "transactions", "transaction_id", transaction_id)
                amount = int(plan.get("amount") or 0)
                if amount <= 0:
                    raise ValueError("transaction amount must be > 0")
                direction = "IN" if old_type == "INCOME" else "OUT"
                category = str(plan.get("transaction_category") or (
                    "GENERAL_INCOME" if old_type == "INCOME" else "NON_CONSTRUCTION_OUTFLOW"
                ))
                con.execute(
                    """UPDATE transactions SET event_date=?, shamsi_date=?, event_time=?, direction=?, amount=?, category=?,
                    payer_name=?, receiver_name=?, description=?, source_type=?, status='POSTED', deleted_at=NULL,
                    sync_status='PENDING', updated_at=? WHERE transaction_id=?""",
                    (event_date, shamsi_date, event_time, direction, amount, category, payer_name, receiver_name,
                     description, source, now, transaction_id),
                )
                sync_update("transaction", transaction_id, old_tx)

            elif old_type == "CHEQUE":
                if not cheque_id:
                    raise ValueError("Cheque لینک‌شده پیدا نشد.")
                old_chq = self._row_dict(con, "cheques", "cheque_id", cheque_id)
                if old_chq.get("status") == "CASHED":
                    raise ValueError("چک پاس‌شده را نمی‌توان با Edit ساده اصلاح کرد.")
                amount = int(plan.get("amount") or 0)
                due_date = str(plan.get("due_date") or "")
                if amount <= 0 or not due_date:
                    raise ValueError("مبلغ و سررسید چک باید مشخص باشد.")
                con.execute(
                    """UPDATE cheques SET amount=?, issue_date=?, issue_date_shamsi=?, due_date=?, due_date_shamsi=?,
                    cheque_serial=?, issuer_bank=?, receiver_name=?, description=?, status='ISSUED', updated_at=? WHERE cheque_id=?""",
                    (amount, event_date, shamsi_date, due_date, plan.get("due_date_shamsi"),
                     plan.get("cheque_serial") or None, plan.get("issuer_bank") or None,
                     receiver_name, description, now, cheque_id),
                )
                sync_update("cheque", cheque_id, old_chq)

            if cheque_id:
                cols={r[1] for r in con.execute("PRAGMA table_info(cheques)").fetchall()}
                if 'registration_state' in cols:
                    con.execute("UPDATE cheques SET issuer_name=?, cheque_type=?, registration_state=?, updated_at=? WHERE cheque_id=?",
                                (str(plan.get('issuer_name') or '').strip() or None,
                                 str(plan.get('cheque_type') or 'PHYSICAL').upper(),
                                 str(plan.get('cheque_registration_state') or 'UNKNOWN').upper(), now, cheque_id))
                else:
                    con.execute("UPDATE cheques SET issuer_name=?, cheque_type=?, updated_at=? WHERE cheque_id=?",
                                (str(plan.get('issuer_name') or '').strip() or None,
                                 str(plan.get('cheque_type') or 'PHYSICAL').upper(), now, cheque_id))

            updated_post = {
                "expense_id": expense_id, "transaction_id": transaction_id,
                "payment_id": payment_id, "cheque_id": cheque_id,
            }
            con.execute(
                """UPDATE financial_postings SET expense_id=?, transaction_id=?, payment_id=?, cheque_id=?,
                plan_json=?, status='ACTIVE', updated_at=? WHERE pending_id=?""",
                (expense_id, transaction_id, payment_id, cheque_id,
                 json.dumps(plan, ensure_ascii=False), now, pending_id),
            )
            con.execute(
                "UPDATE posting_revisions SET status='APPROVED', updated_at=? WHERE revision_id=?",
                (now, revision["revision_id"]),
            )
            new_payload_json = revision["new_payload_json"]
            new_payload = json.loads(new_payload_json)
            con.execute(
                """UPDATE pending_items SET payload_json=?, detected_type=?, confidence=?, status='APPROVED', updated_at=?
                WHERE pending_id=?""",
                (new_payload_json, str(new_payload.get("detected_type") or old_type),
                 float(new_payload.get("confidence")) if new_payload.get("confidence") is not None else item["confidence"],
                 now, pending_id),
            )
            con.execute(
                """UPDATE telegram_messages SET state='APPROVED', linked_entity_type=?, linked_entity_id=?, updated_at=?
                WHERE chat_id=? AND message_id=?""",
                (post["primary_entity_type"], post["primary_entity_id"], now,
                 int(item["telegram_chat_id"]), int(item["telegram_message_id"])),
            )
            before_post = dict(post)
            after_post = dict(con.execute("SELECT * FROM financial_postings WHERE pending_id=?", (pending_id,)).fetchone())
            self._audit(con, "posting", post["posting_id"], "UPDATE", source, before_post, after_post, actor_id)
            self._audit(
                con, "posting_revision", revision["revision_id"], "APPROVE", source,
                before=json.loads(revision["old_payload_json"]), after=new_payload, actor_id=actor_id,
            )
            return after_post

    def delete_financial_posting(self, *, pending_id: str, source: str = "TELEGRAM",
                                 actor_id: Optional[str] = None, reason: str = "") -> dict[str, Any]:
        """Soft-delete one posting and reverse its effect on all derived balances.

        No rows are physically removed from SQLite. Google Sheets receives updated
        VOIDED/CANCELLED state, preserving an audit-friendly mirror. CASHED cheques
        are intentionally blocked because they require an explicit reversal entry.
        """
        now = _now()
        with self.tx() as con:
            post = con.execute("SELECT * FROM financial_postings WHERE pending_id=?", (pending_id,)).fetchone()
            if not post:
                raise KeyError(pending_id)
            if str(post["status"] or "ACTIVE") == "DELETED":
                return dict(post)
            item = con.execute("SELECT * FROM pending_items WHERE pending_id=?", (pending_id,)).fetchone()
            if not item:
                raise KeyError(pending_id)

            expense_id, transaction_id, payment_id, cheque_id = (
                post["expense_id"], post["transaction_id"], post["payment_id"], post["cheque_id"]
            )
            if cheque_id:
                chq = con.execute("SELECT * FROM cheques WHERE cheque_id=?", (cheque_id,)).fetchone()
                if chq and chq["status"] == "CASHED":
                    raise ValueError("ثبت دارای چک پاس‌شده است؛ حذف مستقیم مجاز نیست و باید سند برگشت/اصلاح ثبت شود.")

            if transaction_id:
                old = con.execute("SELECT * FROM transactions WHERE transaction_id=?", (transaction_id,)).fetchone()
                if old and old["status"] != "VOIDED":
                    before = dict(old)
                    con.execute(
                        "UPDATE transactions SET status='VOIDED', deleted_at=?, sync_status='PENDING', updated_at=? WHERE transaction_id=?",
                        (now, now, transaction_id),
                    )
                    after = self._row_dict(con, "transactions", "transaction_id", transaction_id)
                    self._audit(con, "transaction", transaction_id, "VOID", source, before, after, actor_id)
                    self._enqueue_sync(con, "transaction", transaction_id, "DELETE", {"reason": reason})

            if payment_id:
                old = con.execute("SELECT * FROM payments WHERE payment_id=?", (payment_id,)).fetchone()
                if old and old["status"] != "CANCELLED":
                    before = dict(old)
                    con.execute("UPDATE payments SET status='CANCELLED', updated_at=? WHERE payment_id=?", (now, payment_id))
                    after = self._row_dict(con, "payments", "payment_id", payment_id)
                    self._audit(con, "payment", payment_id, "CANCEL", source, before, after, actor_id)
                    self._enqueue_sync(con, "payment", payment_id, "DELETE", {"reason": reason})

            if cheque_id:
                old = con.execute("SELECT * FROM cheques WHERE cheque_id=?", (cheque_id,)).fetchone()
                if old and old["status"] != "CANCELLED":
                    before = dict(old)
                    con.execute("UPDATE cheques SET status='CANCELLED', updated_at=? WHERE cheque_id=?", (now, cheque_id))
                    after = self._row_dict(con, "cheques", "cheque_id", cheque_id)
                    self._audit(con, "cheque", cheque_id, "CANCEL", source, before, after, actor_id)
                    self._enqueue_sync(con, "cheque", cheque_id, "DELETE", {"reason": reason})

            if expense_id:
                old = con.execute("SELECT * FROM expenses WHERE expense_id=?", (expense_id,)).fetchone()
                if old and old["status"] != "CANCELLED":
                    before = dict(old)
                    con.execute(
                        "UPDATE expenses SET status='CANCELLED', deleted_at=?, updated_at=? WHERE expense_id=?",
                        (now, now, expense_id),
                    )
                    after = self._row_dict(con, "expenses", "expense_id", expense_id)
                    self._audit(con, "expense", expense_id, "CANCEL", source, before, after, actor_id)
                    self._enqueue_sync(con, "expense", expense_id, "DELETE", {"reason": reason})

            before_post = dict(post)
            con.execute(
                "UPDATE financial_postings SET status='DELETED', deleted_at=?, updated_at=? WHERE pending_id=?",
                (now, now, pending_id),
            )
            con.execute(
                """UPDATE telegram_messages SET state='DELETED', reaction_state='NONE', updated_at=?
                WHERE chat_id=? AND message_id=?""",
                (now, int(item["telegram_chat_id"]), int(item["telegram_message_id"])),
            )
            # Any not-yet-approved edit is cancelled as part of deletion.
            con.execute(
                "UPDATE posting_revisions SET status='REJECTED', updated_at=? WHERE pending_id=? AND status='PENDING'",
                (now, pending_id),
            )
            after_post = dict(con.execute("SELECT * FROM financial_postings WHERE pending_id=?", (pending_id,)).fetchone())
            if reason:
                after_post["delete_reason"] = reason
            self._audit(con, "posting", post["posting_id"], "DELETE", source, before_post, after_post, actor_id)
            return after_post

    # ---------- Stage 6 cheque lifecycle / reminders ----------
    def get_cheque(self, cheque_id: str) -> Optional[dict[str, Any]]:
        with self.read() as con:
            row = con.execute("SELECT * FROM cheques WHERE cheque_id=?", (cheque_id,)).fetchone()
            return dict(row) if row else None

    def list_cheques(self, *, open_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        where = "WHERE status IN ('ISSUED','PENDING_DUE','RETURNED')" if open_only else ""
        with self.read() as con:
            rows = con.execute(
                f"SELECT * FROM cheques {where} ORDER BY due_date ASC, created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_cheque_details(self, cheque_id: str, *, amount: Optional[int] = None,
                              issue_date: Optional[str] = None, issue_date_shamsi: Optional[str] = None,
                              due_date: Optional[str] = None, due_date_shamsi: Optional[str] = None,
                              cheque_serial: Optional[str] = None, issuer_bank: Optional[str] = None,
                              issuer_name: Optional[str] = None, cheque_type: Optional[str] = None,
                              receiver_name: Optional[str] = None, description: Optional[str] = None, is_guarantee: Optional[bool] = None,
                              source: str = 'GUI', actor_id: Optional[str] = None) -> dict[str, Any]:
        with self.tx() as con:
            row=con.execute('SELECT * FROM cheques WHERE cheque_id=?',(cheque_id,)).fetchone()
            if not row: raise KeyError(cheque_id)
            if row['status']=='CASHED': raise ValueError('چک پاس‌شده فقط از مسیر اصلاح تخصصی قابل تغییر است.')
            before=dict(row); fields=[]; vals=[]
            for k,v in [('amount',amount),('issue_date',issue_date),('issue_date_shamsi',issue_date_shamsi),('due_date',due_date),('due_date_shamsi',due_date_shamsi),
                        ('cheque_serial',cheque_serial),('issuer_bank',issuer_bank),('issuer_name',issuer_name),
                        ('cheque_type',cheque_type),('receiver_name',receiver_name),('description',description),('is_guarantee',None if is_guarantee is None else (1 if is_guarantee else 0))]:
                if v is None: continue
                if k=='amount': v=int(v)
                if k=='cheque_type':
                    v=str(v or 'PHYSICAL').upper()
                    if v not in ('PHYSICAL','DIGITAL'): raise ValueError('نوع چک باید PHYSICAL یا DIGITAL باشد.')
                fields.append(f'{k}=?'); vals.append(v)
            if fields:
                fields.append('updated_at=?');vals.append(_now());vals.append(cheque_id)
                con.execute(f"UPDATE cheques SET {','.join(fields)} WHERE cheque_id=?",vals)
                after=dict(con.execute('SELECT * FROM cheques WHERE cheque_id=?',(cheque_id,)).fetchone())
                self._audit(con,'cheque',cheque_id,'UPDATE',source,before,after,actor_id)
                self._enqueue_sync(con,'cheque',cheque_id,'UPDATE',after)
                return after
            return before

    def mark_cheque_pending_due(self, cheque_id: str, *, source: str = "SYSTEM",
                                actor_id: Optional[str] = None) -> bool:
        """Move an issued cheque into PENDING_DUE without changing financial amounts."""
        with self.tx() as con:
            row = con.execute("SELECT * FROM cheques WHERE cheque_id=?", (cheque_id,)).fetchone()
            if not row:
                raise KeyError(cheque_id)
            if row["status"] != "ISSUED":
                return False
            before = dict(row)
            now = _now()
            con.execute("UPDATE cheques SET status='PENDING_DUE', updated_at=? WHERE cheque_id=?", (now, cheque_id))
            after = dict(con.execute("SELECT * FROM cheques WHERE cheque_id=?", (cheque_id,)).fetchone())
            self._audit(con, "cheque", cheque_id, "PENDING_DUE", source, before=before, after=after, actor_id=actor_id)
            self._enqueue_sync(con, "cheque", cheque_id, "UPDATE", after)
            return True

    def return_cheque(self, cheque_id: str, *, source: str = "SYSTEM",
                      actor_id: Optional[str] = None) -> bool:
        """Mark a cheque returned/bounced. No cash transaction is created.

        The construction expense stays realized and the returned cheque remains an
        outstanding commitment until it is later cashed or explicitly cancelled.
        """
        with self.tx() as con:
            row = con.execute("SELECT * FROM cheques WHERE cheque_id=?", (cheque_id,)).fetchone()
            if not row:
                raise KeyError(cheque_id)
            if row["status"] == "RETURNED":
                return False
            if row["status"] == "CASHED":
                raise ValueError("cashed cheque cannot be marked returned")
            if row["status"] == "CANCELLED":
                raise ValueError("cancelled cheque cannot be marked returned")
            before = dict(row)
            now = _now()
            con.execute("UPDATE cheques SET status='RETURNED', updated_at=? WHERE cheque_id=?", (now, cheque_id))
            after = dict(con.execute("SELECT * FROM cheques WHERE cheque_id=?", (cheque_id,)).fetchone())
            self._audit(con, "cheque", cheque_id, "RETURN", source, before=before, after=after, actor_id=actor_id)
            self._enqueue_sync(con, "cheque", cheque_id, "UPDATE", after)
            # Pre-due reminders are no longer useful after an explicit returned status.
            con.execute(
                "UPDATE reminders SET status='CANCELLED', updated_at=? "
                "WHERE entity_type='CHEQUE' AND entity_id=? AND status='SCHEDULED'",
                (now, cheque_id),
            )
            return True

    def cancel_cheque(self, cheque_id: str, *, source: str = "SYSTEM",
                      actor_id: Optional[str] = None) -> bool:
        """Cancel an uncashed cheque without cancelling the underlying expense.

        The linked cheque Payment is cancelled and the expense returns to its
        correct unpaid/partially-paid state. Cash and manager fee are not changed.
        """
        with self.tx() as con:
            row = con.execute("SELECT * FROM cheques WHERE cheque_id=?", (cheque_id,)).fetchone()
            if not row:
                raise KeyError(cheque_id)
            if row["status"] == "CANCELLED":
                return False
            if row["status"] == "CASHED":
                raise ValueError("cashed cheque cannot be cancelled directly")
            before = dict(row)
            now = _now()
            con.execute("UPDATE cheques SET status='CANCELLED', updated_at=? WHERE cheque_id=?", (now, cheque_id))
            payment = con.execute(
                "SELECT * FROM payments WHERE cheque_id=? AND status!='CANCELLED' ORDER BY created_at LIMIT 1",
                (cheque_id,),
            ).fetchone()
            if payment:
                p_before = dict(payment)
                con.execute(
                    "UPDATE payments SET status='CANCELLED', transaction_id=NULL, updated_at=? WHERE payment_id=?",
                    (now, payment["payment_id"]),
                )
                p_after = dict(con.execute("SELECT * FROM payments WHERE payment_id=?", (payment["payment_id"],)).fetchone())
                self._audit(con, "payment", payment["payment_id"], "CANCEL_CHEQUE_PAYMENT", source,
                            before=p_before, after=p_after, actor_id=actor_id)
                self._enqueue_sync(con, "payment", payment["payment_id"], "UPDATE", p_after)
            if row["expense_id"]:
                self._refresh_expense_payment_status(con, row["expense_id"])
                exp = con.execute("SELECT * FROM expenses WHERE expense_id=?", (row["expense_id"],)).fetchone()
                if exp:
                    self._enqueue_sync(con, "expense", row["expense_id"], "UPDATE", dict(exp))
            after = dict(con.execute("SELECT * FROM cheques WHERE cheque_id=?", (cheque_id,)).fetchone())
            self._audit(con, "cheque", cheque_id, "CANCEL", source, before=before, after=after, actor_id=actor_id)
            self._enqueue_sync(con, "cheque", cheque_id, "UPDATE", after)
            con.execute(
                "UPDATE reminders SET status='CANCELLED', updated_at=? "
                "WHERE entity_type='CHEQUE' AND entity_id=? AND status='SCHEDULED'",
                (now, cheque_id),
            )
            return True

    def settle_returned_cheque(self, cheque_id: str, *, settled_date: str, settled_date_shamsi: Optional[str] = None,
                                source: str = "GUI", actor_id: Optional[str] = None) -> str:
        """Settle a returned cheque by a replacement bank transfer.

        Financially this closes the same payable as a cashed cheque, but the
        settlement transaction is recorded as a bank-transfer payment and the
        cheque keeps a display settlement_mode=RETURNED_SETTLED for audit/UI.
        """
        with self.tx() as con:
            chq = con.execute("SELECT * FROM cheques WHERE cheque_id=?", (cheque_id,)).fetchone()
            if not chq:
                raise KeyError(cheque_id)
            if int(chq["is_guarantee"] or 0):
                raise ValueError("چک ضمانتی از مسیر تسویه مالی عودتی ثبت نمی‌شود.")
            if chq["status"] == "CANCELLED":
                raise ValueError("چک باطل‌شده قابل تسویه نیست.")
            if chq["status"] == "CASHED" and chq["cash_transaction_id"]:
                con.execute("UPDATE cheques SET settlement_mode='RETURNED_SETTLED',updated_at=? WHERE cheque_id=?", (_now(), cheque_id))
                return chq["cash_transaction_id"]
            tx_id = _id("TX")
            now = _now()
            con.execute(
                """INSERT INTO transactions(transaction_id,event_date,shamsi_date,direction,amount,category,
                receiver_name,description,source_type,expense_id,status,sync_status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?, 'POSTED','PENDING',?,?)""",
                (tx_id, settled_date, settled_date_shamsi, "OUT", chq["amount"], "EXPENSE_PAYMENT_TRANSFER",
                 chq["receiver_name"], (chq["description"] or "") + " — عودت چک و تسویه با واریز", source, chq["expense_id"], now, now),
            )
            con.execute(
                "UPDATE cheques SET status='CASHED', settlement_mode='RETURNED_SETTLED', cashed_date=?, cashed_date_shamsi=?, cash_transaction_id=?, updated_at=? WHERE cheque_id=?",
                (settled_date, settled_date_shamsi, tx_id, now, cheque_id),
            )
            if chq["expense_id"]:
                payment = con.execute("SELECT payment_id FROM payments WHERE cheque_id=? AND status!='CANCELLED' LIMIT 1", (cheque_id,)).fetchone()
                if payment:
                    con.execute("UPDATE payments SET transaction_id=?, status='COMPLETED', updated_at=? WHERE payment_id=?", (tx_id, now, payment["payment_id"]))
                    prow=dict(con.execute("SELECT * FROM payments WHERE payment_id=?",(payment["payment_id"],)).fetchone())
                    self._enqueue_sync(con,"payment",payment["payment_id"],"UPDATE",prow)
                    self._refresh_expense_payment_status(con,chq["expense_id"])
            con.execute("UPDATE reminders SET status='CANCELLED',updated_at=? WHERE entity_type='CHEQUE' AND entity_id=? AND status='SCHEDULED'", (now,cheque_id))
            after=dict(con.execute("SELECT * FROM cheques WHERE cheque_id=?",(cheque_id,)).fetchone())
            txrow=dict(con.execute("SELECT * FROM transactions WHERE transaction_id=?",(tx_id,)).fetchone())
            self._audit(con,"cheque",cheque_id,"RETURNED_SETTLED",source,before=dict(chq),after=after,actor_id=actor_id)
            self._audit(con,"transaction",tx_id,"CREATE",source,after=txrow,actor_id=actor_id)
            self._enqueue_sync(con,"cheque",cheque_id,"UPDATE",after)
            self._enqueue_sync(con,"transaction",tx_id,"CREATE",txrow)
            return tx_id

    def set_cheque_lifecycle_status(self, cheque_id: str, status: str, *,
                                    event_date: Optional[str] = None,
                                    event_date_shamsi: Optional[str] = None,
                                    source: str = "GUI",
                                    actor_id: Optional[str] = None) -> dict[str, Any]:
        """Set a cheque lifecycle state through audited, accounting-safe transitions.

        This is the public GUI path for manual status correction.  It deliberately
        routes RETURNED/CANCELLED/CASHED through their existing domain methods so
        cash, payment and reminder side effects cannot be skipped.  Re-opening a
        CASHED/CANCELLED cheque is blocked because that requires a dedicated reversal.
        """
        target = str(status or '').upper().strip()
        if target not in {'ISSUED','PENDING_DUE','CASHED','RETURNED','CANCELLED'}:
            raise ValueError('invalid cheque lifecycle status')
        row = self.get_cheque(cheque_id)
        if not row:
            raise KeyError(cheque_id)
        current = str(row.get('status') or '').upper()
        if target == current:
            return row
        if current in {'CASHED','CANCELLED'}:
            raise ValueError('چک پاس‌شده/لغوشده برای تغییر وضعیت نیاز به عملیات برگشت تخصصی دارد.')
        if target == 'CASHED':
            if int(row.get('is_guarantee') or 0):
                raise ValueError('چک ضمانتی از مسیر مالی «پاس‌شده» ثبت نمی‌شود؛ وضعیت ضمانت را عودت/لغو کن.')
            if not event_date:
                raise ValueError('برای وضعیت پاس‌شده، تاریخ پاس شدن الزامی است.')
            self.cash_cheque(cheque_id, cashed_date=event_date, cashed_date_shamsi=event_date_shamsi,
                             source=source, actor_id=actor_id)
            return self.get_cheque(cheque_id) or {}
        if target == 'RETURNED':
            self.return_cheque(cheque_id, source=source, actor_id=actor_id)
            return self.get_cheque(cheque_id) or {}
        if target == 'CANCELLED':
            self.cancel_cheque(cheque_id, source=source, actor_id=actor_id)
            return self.get_cheque(cheque_id) or {}

        # ISSUED/PENDING_DUE are non-cash lifecycle states.  Directly changing
        # between them (or re-presenting a returned cheque) has no financial
        # amount side effect, but is still audited and synced.
        with self.tx() as con:
            old = con.execute('SELECT * FROM cheques WHERE cheque_id=?', (cheque_id,)).fetchone()
            if not old:
                raise KeyError(cheque_id)
            before = dict(old); now = _now()
            con.execute('UPDATE cheques SET status=?,updated_at=? WHERE cheque_id=?', (target, now, cheque_id))
            after = dict(con.execute('SELECT * FROM cheques WHERE cheque_id=?', (cheque_id,)).fetchone())
            self._audit(con, 'cheque', cheque_id, 'SET_STATUS', source, before=before, after=after, actor_id=actor_id)
            self._enqueue_sync(con, 'cheque', cheque_id, 'UPDATE', after)
            if target == 'ISSUED':
                # Old scheduled reminders may have been cancelled by RETURNED;
                # the normal reminder scheduler can recreate them idempotently.
                pass
            return after

    def ensure_cheque_reminders(self, cheque_id: str, *, reminder_times: Iterable[str],
                                days_before: int = 5, telegram: bool = True,
                                email: bool = False) -> int:
        """Create missing reminder rows from N days before due date through due day.

        Times are supplied by configuration and are never hard-coded into the
        ledger. Existing rows are detected by scheduled_at/channel tuple so the
        operation is idempotent across restarts.
        """
        chq = self.get_cheque(cheque_id)
        if not chq:
            raise KeyError(cheque_id)
        if chq["status"] in {"CASHED", "CANCELLED"}:
            return 0
        due = date.fromisoformat(str(chq["due_date"]))
        days_before = max(0, int(days_before))
        parsed_times: list[tuple[int, int]] = []
        for raw in reminder_times:
            text = str(raw).strip()
            if not text:
                continue
            try:
                hh_s, mm_s = text.split(":", 1)
                hh, mm = int(hh_s), int(mm_s)
            except Exception as exc:
                raise ValueError(f"invalid reminder time: {text}") from exc
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError(f"invalid reminder time: {text}")
            parsed_times.append((hh, mm))
        if not parsed_times:
            return 0

        created = 0
        now = _now()
        with self.tx() as con:
            for offset in range(days_before, -1, -1):
                day = due - timedelta(days=offset)
                for hh, mm in parsed_times:
                    scheduled = datetime.combine(day, datetime.min.time()).replace(hour=hh, minute=mm).isoformat(timespec="seconds")
                    exists = con.execute(
                        "SELECT reminder_id FROM reminders WHERE entity_type='CHEQUE' AND entity_id=? "
                        "AND scheduled_at=? AND channel_telegram=? AND channel_email=? LIMIT 1",
                        (cheque_id, scheduled, int(bool(telegram)), int(bool(email))),
                    ).fetchone()
                    if exists:
                        continue
                    reminder_id = _id("REM")
                    con.execute(
                        "INSERT INTO reminders(reminder_id,entity_type,entity_id,scheduled_at,channel_telegram,channel_email,status,created_at,updated_at) "
                        "VALUES(?,?,?,?,?,?, 'SCHEDULED', ?, ?)",
                        (reminder_id, "CHEQUE", cheque_id, scheduled, int(bool(telegram)), int(bool(email)), now, now),
                    )
                    created += 1
        return created

    def ensure_all_open_cheque_reminders(self, *, reminder_times: Iterable[str], days_before: int = 5,
                                         telegram: bool = True, email: bool = False) -> int:
        total = 0
        for chq in self.list_cheques(open_only=True, limit=1000):
            total += self.ensure_cheque_reminders(
                chq["cheque_id"], reminder_times=reminder_times, days_before=days_before,
                telegram=telegram, email=email,
            )
        return total

    def get_due_cheque_reminders(self, now_iso: Optional[str] = None, *, limit: int = 20) -> list[dict[str, Any]]:
        now_iso = now_iso or _now()
        limit = max(1, min(int(limit), 200))
        with self.read() as con:
            rows = con.execute(
                "SELECT r.*, c.amount, c.due_date, c.due_date_shamsi, c.receiver_name, c.description, c.status AS cheque_status "
                "FROM reminders r JOIN cheques c ON c.cheque_id=r.entity_id "
                "WHERE r.entity_type='CHEQUE' AND r.status='SCHEDULED' AND r.scheduled_at<=? "
                "AND c.status IN ('ISSUED','PENDING_DUE') ORDER BY r.scheduled_at, r.reminder_id LIMIT ?",
                (now_iso, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_reminder_sent(self, reminder_id: str, *, channel: str = "TELEGRAM", details: str = "") -> None:
        now = _now()
        with self.tx() as con:
            con.execute("UPDATE reminders SET status='SENT', updated_at=? WHERE reminder_id=?", (now, reminder_id))
            con.execute(
                "INSERT INTO reminder_log(reminder_id,sent_at,channel,success,details) VALUES(?,?,?,?,?)",
                (reminder_id, now, channel, 1, details[:1000]),
            )

    def log_reminder_failure(self, reminder_id: str, *, channel: str = "TELEGRAM", details: str = "") -> None:
        now = _now()
        with self.tx() as con:
            # Keep SCHEDULED for retry; only record the failed attempt.
            con.execute("UPDATE reminders SET updated_at=? WHERE reminder_id=?", (now, reminder_id))
            con.execute(
                "INSERT INTO reminder_log(reminder_id,sent_at,channel,success,details) VALUES(?,?,?,?,?)",
                (reminder_id, now, channel, 0, details[:1000]),
            )

    def cancel_future_cheque_reminders(self, cheque_id: str) -> int:
        now = _now()
        with self.tx() as con:
            cur = con.execute(
                "UPDATE reminders SET status='CANCELLED', updated_at=? "
                "WHERE entity_type='CHEQUE' AND entity_id=? AND status='SCHEDULED'",
                (now, cheque_id),
            )
            return int(cur.rowcount or 0)

    def reminder_counts(self) -> dict[str, int]:
        with self.read() as con:
            rows = con.execute("SELECT status, COUNT(*) c FROM reminders GROUP BY status").fetchall()
        return {r["status"]: int(r["c"]) for r in rows}

    def expire_stale_cheque_reminders(self, before_iso: str) -> int:
        """Cancel old unsent reminder slots so a restart never floods the admin."""
        now = _now()
        with self.tx() as con:
            cur = con.execute(
                "UPDATE reminders SET status='CANCELLED', updated_at=? "
                "WHERE entity_type='CHEQUE' AND status='SCHEDULED' AND scheduled_at<?",
                (now, before_iso),
            )
            return int(cur.rowcount or 0)

    # ---------- derived calculations ----------
    def cash_balance(self, as_of: Optional[str] = None) -> int:
        where = "status='POSTED' AND deleted_at IS NULL"
        params: list[Any] = []
        if as_of:
            where += " AND event_date<=?"
            params.append(as_of)
        with self.read() as con:
            row = con.execute(
                f"SELECT COALESCE(SUM(CASE WHEN direction='IN' THEN amount ELSE -amount END),0) FROM transactions WHERE {where}",
                params,
            ).fetchone()
            return int(row[0] or 0)

    def construction_cost(self, as_of: Optional[str] = None) -> int:
        where = "status IN ('APPROVED','PARTIALLY_PAID','PAID') AND deleted_at IS NULL"
        params: list[Any] = []
        if as_of:
            where += " AND event_date<=?"
            params.append(as_of)
        with self.read() as con:
            return int(con.execute(f"SELECT COALESCE(SUM(final_amount),0) FROM expenses WHERE {where}", params).fetchone()[0] or 0)

    def manager_fee_accrued(self, as_of: Optional[str] = None) -> int:
        bps = int(self.get_setting("manager_fee_bps", str(DEFAULT_MANAGER_FEE_BPS)))
        where = "manager_fee_eligible=1 AND status IN ('APPROVED','PARTIALLY_PAID','PAID') AND deleted_at IS NULL"
        params: list[Any] = []
        if as_of:
            where += " AND event_date<=?"
            params.append(as_of)
        with self.read() as con:
            total = int(con.execute(f"SELECT COALESCE(SUM(final_amount),0) FROM expenses WHERE {where}", params).fetchone()[0] or 0)
        return (total * bps) // 10000

    def manager_withdrawals(self, as_of: Optional[str] = None) -> int:
        where = "status='POSTED' AND deleted_at IS NULL AND direction='OUT' AND category='CONTRACTOR_FEE'"
        params: list[Any] = []
        if as_of:
            where += " AND event_date<=?"
            params.append(as_of)
        with self.read() as con:
            return int(con.execute(f"SELECT COALESCE(SUM(amount),0) FROM transactions WHERE {where}", params).fetchone()[0] or 0)

    def open_cheque_commitments(self, as_of: Optional[str] = None) -> int:
        where = "status IN ('ISSUED','PENDING_DUE','RETURNED') AND COALESCE(is_guarantee,0)=0"
        params: list[Any] = []
        if as_of:
            where += " AND issue_date<=?"
            params.append(as_of)
        with self.read() as con:
            return int(con.execute(f"SELECT COALESCE(SUM(amount),0) FROM cheques WHERE {where}", params).fetchone()[0] or 0)

    def snapshot(self, as_of: Optional[str] = None) -> FinancialSnapshot:
        cash = self.cash_balance(as_of)
        cost = self.construction_cost(as_of)
        fee = self.manager_fee_accrued(as_of)
        withdrawals = self.manager_withdrawals(as_of)
        manager_balance = fee - withdrawals
        commitments = self.open_cheque_commitments(as_of)
        return FinancialSnapshot(
            cash_balance=cash,
            construction_cost=cost,
            manager_fee_accrued=fee,
            manager_withdrawals=withdrawals,
            manager_balance=manager_balance,
            open_cheque_commitments=commitments,
            free_cash_after_cheques=cash - commitments,
        )

    def manager_exposure(self, start_date: str, end_date: str) -> ManagerExposure:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        if end < start:
            raise ValueError("end_date must be >= start_date")

        creditor_days = debtor_days = neutral_days = 0
        creditor_td = debtor_td = 0
        current = start
        while current <= end:
            bal = self.manager_fee_accrued(current.isoformat()) - self.manager_withdrawals(current.isoformat())
            if bal > 0:
                creditor_days += 1
                creditor_td += bal
            elif bal < 0:
                debtor_days += 1
                debtor_td += abs(bal)
            else:
                neutral_days += 1
            current += timedelta(days=1)

        avg_credit = creditor_td // creditor_days if creditor_days else 0
        avg_debit = debtor_td // debtor_days if debtor_days else 0
        return ManagerExposure(
            start_date=start_date,
            end_date=end_date,
            creditor_days=creditor_days,
            debtor_days=debtor_days,
            neutral_days=neutral_days,
            creditor_toman_days=creditor_td,
            debtor_toman_days=debtor_td,
            net_toman_days=creditor_td - debtor_td,
            average_creditor_balance=avg_credit,
            average_debtor_balance=avg_debit,
        )

    def health_check(self) -> dict[str, Any]:
        with self.read() as con:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            pending_sync = con.execute("SELECT COUNT(*) FROM sync_queue WHERE status!='SYNCED'").fetchone()[0]
            duplicate_tg = con.execute(
                "SELECT COUNT(*) FROM (SELECT chat_id,message_id,COUNT(*) c FROM telegram_messages GROUP BY chat_id,message_id HAVING c>1)"
            ).fetchone()[0]
            schema_version = con.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()[0]
        return {
            "sqlite_integrity": integrity,
            "schema_version": int(schema_version),
            "pending_sync_items": int(pending_sync),
            "duplicate_telegram_messages": int(duplicate_tg),
        }
