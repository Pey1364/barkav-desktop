from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

from cheque_status187 import open_sql as _cheque_open_sql
from edit_normalizer import normalize_financial_edit
from finance_db import FinanceDB, _id, _now
from financial_posting import build_posting_plan
from revenue_service import RevenueService, gregorian_to_shamsi, normalize_shamsi, shamsi_to_gregorian


@dataclass(frozen=True)
class DashboardOverview:
    cash_balance: int
    construction_cost: int
    manager_fee_accrued: int
    manager_withdrawals: int
    manager_balance: int
    open_cheque_commitments: int
    free_cash_after_cheques: int
    contract_sales: int
    buyer_cash_received: int
    buyer_receivable: int
    buyer_overdue: int
    unmatched_received: int
    active_sales: int
    pending_sync: int
    failed_sync: int
    sqlite_integrity: str
    bank_balance: Optional[int]
    bank_difference: Optional[int]
    bank_reconciled_shamsi: str


class DashboardService:
    """Read/write facade for the Stage 8 management GUI.

    SQLite remains the sole source of truth. All edits/deletes reuse the Stage 5
    revision engine so linked Expense/Payment/Transaction/Cheque IDs stay stable
    and Google Sheets receives ordinary sync-queue updates.
    """

    def __init__(self, db: FinanceDB):
        self.db = db
        self.revenue = RevenueService(db)

    # ---------- overview ----------
    def overview(self) -> DashboardOverview:
        snap = self.db.snapshot()
        buyer = self.revenue.buyer_dashboard()
        health = self.db.health_check()
        with self.db.read() as con:
            failed = int(con.execute("SELECT COUNT(*) FROM sync_queue WHERE status='FAILED'").fetchone()[0] or 0)
            rec = con.execute(
                "SELECT * FROM reconciliations WHERE deleted_at IS NULL ORDER BY event_date DESC, created_at DESC LIMIT 1"
            ).fetchone()
        return DashboardOverview(
            cash_balance=snap.cash_balance,
            construction_cost=snap.construction_cost,
            manager_fee_accrued=snap.manager_fee_accrued,
            manager_withdrawals=snap.manager_withdrawals,
            manager_balance=snap.manager_balance,
            open_cheque_commitments=snap.open_cheque_commitments,
            free_cash_after_cheques=snap.free_cash_after_cheques,
            contract_sales=int(buyer['contract_sales']),
            buyer_cash_received=int(buyer['cash_received']),
            buyer_receivable=int(buyer['receivable']),
            buyer_overdue=int(buyer['overdue']),
            unmatched_received=int(buyer['unmatched_received']),
            active_sales=int(buyer['active_sales']),
            pending_sync=int(health['pending_sync_items']),
            failed_sync=failed,
            sqlite_integrity=str(health['sqlite_integrity']),
            bank_balance=int(rec['bank_balance']) if rec else None,
            bank_difference=int(rec['difference']) if rec else None,
            bank_reconciled_shamsi=str(rec['shamsi_date'] or '') if rec else '',
        )

    # ---------- reconciliation ----------
    def record_reconciliation(self, *, bank_balance: int, shamsi_date: str = '', notes: str = '') -> dict[str, Any]:
        if not shamsi_date:
            shamsi_date = gregorian_to_shamsi(date.today())
        shamsi_date = normalize_shamsi(shamsi_date)
        if not shamsi_date:
            raise ValueError('تاریخ شمسی نامعتبر است.')
        event_date = shamsi_to_gregorian(shamsi_date)
        system_balance = self.db.cash_balance(event_date)
        bank_balance = int(bank_balance)
        row = {
            'reconciliation_id': _id('REC'),
            'event_date': event_date,
            'shamsi_date': shamsi_date,
            'system_balance': int(system_balance),
            'bank_balance': bank_balance,
            'difference': bank_balance - int(system_balance),
            'notes': (notes or '').strip(),
            'created_at': _now(),
            'updated_at': _now(),
        }
        with self.db.tx() as con:
            con.execute(
                """INSERT INTO reconciliations(reconciliation_id,event_date,shamsi_date,system_balance,
                   bank_balance,difference,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                tuple(row[k] for k in ['reconciliation_id','event_date','shamsi_date','system_balance','bank_balance','difference','notes','created_at','updated_at']),
            )
            self.db._audit(con, 'reconciliation', row['reconciliation_id'], 'CREATE', 'GUI', after=row, actor_id='GUI')
        return row

    def list_reconciliations(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.db.read() as con:
            rows = con.execute(
                "SELECT * FROM reconciliations WHERE deleted_at IS NULL ORDER BY event_date DESC, created_at DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [dict(r) for r in rows]


    def update_reconciliation(self, reconciliation_id: str, *, bank_balance: int, shamsi_date: str, notes: str = '') -> dict[str, Any]:
        shamsi_date = normalize_shamsi(shamsi_date)
        if not shamsi_date:
            raise ValueError('تاریخ شمسی نامعتبر است.')
        event_date = shamsi_to_gregorian(shamsi_date)
        bank_balance = int(bank_balance)
        system_balance = int(self.db.cash_balance(event_date))
        with self.db.tx() as con:
            old = con.execute("SELECT * FROM reconciliations WHERE reconciliation_id=? AND deleted_at IS NULL", (reconciliation_id,)).fetchone()
            if not old:
                raise KeyError(reconciliation_id)
            before = dict(old); now = _now()
            con.execute("""UPDATE reconciliations SET event_date=?,shamsi_date=?,system_balance=?,bank_balance=?,difference=?,notes=?,updated_at=?
                           WHERE reconciliation_id=?""",
                        (event_date, shamsi_date, system_balance, bank_balance, bank_balance-system_balance, (notes or '').strip(), now, reconciliation_id))
            after = dict(con.execute("SELECT * FROM reconciliations WHERE reconciliation_id=?", (reconciliation_id,)).fetchone())
            self.db._audit(con, 'reconciliation', reconciliation_id, 'UPDATE', 'GUI', before=before, after=after, actor_id='GUI')
        return after

    def delete_reconciliation(self, reconciliation_id: str) -> None:
        with self.db.tx() as con:
            old = con.execute("SELECT * FROM reconciliations WHERE reconciliation_id=? AND deleted_at IS NULL", (reconciliation_id,)).fetchone()
            if not old:
                raise KeyError(reconciliation_id)
            now = _now()
            con.execute("UPDATE reconciliations SET deleted_at=?,updated_at=? WHERE reconciliation_id=?", (now, now, reconciliation_id))
            self.db._audit(con, 'reconciliation', reconciliation_id, 'DELETE', 'GUI', before=dict(old), after={'deleted_at': now}, actor_id='GUI')

    # ---------- manager account ----------
    def manager_activity_bounds(self) -> tuple[str, str]:
        with self.db.read() as con:
            first_exp = con.execute(
                "SELECT MIN(event_date) FROM expenses WHERE manager_fee_eligible=1 AND status!='CANCELLED' AND deleted_at IS NULL"
            ).fetchone()[0]
            first_wd = con.execute(
                "SELECT MIN(event_date) FROM transactions WHERE category='CONTRACTOR_FEE' AND status='POSTED' AND deleted_at IS NULL"
            ).fetchone()[0]
        first = min([x for x in [first_exp, first_wd] if x], default=date.today().isoformat())
        return gregorian_to_shamsi(first), gregorian_to_shamsi(date.today())

    def manager_exposure_shamsi(self, start_shamsi: str, end_shamsi: str):
        start = shamsi_to_gregorian(start_shamsi)
        end = shamsi_to_gregorian(end_shamsi)
        return self.db.manager_exposure(start, end)

    def manager_daily_series(self, start_shamsi: str, end_shamsi: str) -> list[dict[str, Any]]:
        start = date.fromisoformat(shamsi_to_gregorian(start_shamsi))
        end = date.fromisoformat(shamsi_to_gregorian(end_shamsi))
        if end < start:
            raise ValueError('تاریخ پایان قبل از تاریخ شروع است.')
        if (end - start).days > 3650:
            raise ValueError('بازه نمودار حداکثر ۱۰ سال است.')
        bps = int(self.db.get_setting('manager_fee_bps', '1000') or 1000)
        with self.db.read() as con:
            exp_rows = con.execute(
                """SELECT event_date,COALESCE(SUM(final_amount),0) v FROM expenses
                   WHERE manager_fee_eligible=1 AND status IN ('APPROVED','PARTIALLY_PAID','PAID')
                     AND deleted_at IS NULL AND event_date<=? GROUP BY event_date ORDER BY event_date""",
                (end.isoformat(),),
            ).fetchall()
            wd_rows = con.execute(
                """SELECT event_date,COALESCE(SUM(amount),0) v FROM transactions
                   WHERE category='CONTRACTOR_FEE' AND direction='OUT' AND status='POSTED'
                     AND deleted_at IS NULL AND event_date<=? GROUP BY event_date ORDER BY event_date""",
                (end.isoformat(),),
            ).fetchall()
        exp_by = {str(r['event_date']): int(r['v'] or 0) for r in exp_rows}
        wd_by = {str(r['event_date']): int(r['v'] or 0) for r in wd_rows}
        # Include all events before start in the opening balance.
        cursor = min(
            [date.fromisoformat(x) for x in list(exp_by) + list(wd_by)] or [start]
        )
        total_eligible = 0
        withdrawals = 0
        while cursor < start:
            k = cursor.isoformat()
            total_eligible += exp_by.get(k, 0)
            withdrawals += wd_by.get(k, 0)
            cursor += timedelta(days=1)
        out: list[dict[str, Any]] = []
        cursor = start
        while cursor <= end:
            k = cursor.isoformat()
            total_eligible += exp_by.get(k, 0)
            withdrawals += wd_by.get(k, 0)
            fee = (total_eligible * bps) // 10000
            out.append({
                'date': k,
                'shamsi_date': gregorian_to_shamsi(cursor),
                'balance': fee - withdrawals,
                'fee_accrued': fee,
                'withdrawals': withdrawals,
            })
            cursor += timedelta(days=1)
        return out

    # ---------- lists ----------
    def list_cheques(self, *, open_only: bool = False, limit: int = 500) -> list[dict[str, Any]]:
        where = f"WHERE {_cheque_open_sql('c')}" if open_only else ''
        with self.db.read() as con:
            rows = [dict(r) for r in con.execute(
                f"""SELECT c.*,e.category expense_category,e.description expense_description
                    FROM cheques c LEFT JOIN expenses e ON e.expense_id=c.expense_id
                    {where} ORDER BY c.due_date DESC,c.cheque_id DESC LIMIT ?""", (int(limit),)
            ).fetchall()]
            # A cheque row a record's approval made and a later approval took back stays in the database as
            # «لغوشده» for the audit trail, but it belongs to no record and is not a row of the cheque tab.
            # «باطل‌شده» (a resolution) is a row, and so is a cheque cancelled on purpose while its record stands.
            taken_back = [r for r in rows if r['status'] in ('CANCELLED', 'VOIDED') and r.get('settlement_mode') != 'VOIDED']
            if taken_back:
                from record_ownership187 import owned_keys
                owned = owned_keys(con)['cheques']
                gone = {r['cheque_id'] for r in taken_back if r['cheque_id'] not in owned}
                rows = [r for r in rows if r['cheque_id'] not in gone]
        return rows

    def list_sales_summary(self, limit: int = 500) -> list[dict[str, Any]]:
        rows = self.revenue.list_sales(limit=limit)
        out = []
        for sale in rows:
            s = self.revenue.sale_summary(str(sale['sale_id']))
            item = dict(sale)
            item.update({
                'cash_received': s.cash_received,
                'receivable': s.receivable,
                'overdue_amount': s.overdue_amount,
                'next_due_shamsi': s.next_due_shamsi,
                'next_due_amount': s.next_due_amount,
            })
            out.append(item)
        return out

    def list_postings(self, *, include_deleted: bool = False, limit: int = 1000) -> list[dict[str, Any]]:
        where = '' if include_deleted else "WHERE COALESCE(fp.status,'ACTIVE')='ACTIVE'"
        with self.db.read() as con:
            rows = con.execute(
                f"""SELECT fp.*,pi.payload_json,pi.telegram_chat_id,pi.telegram_message_id,
                    e.final_amount expense_amount,e.description expense_description,e.status expense_status,
                    t.amount transaction_amount,t.direction,t.category transaction_category,t.description transaction_description,t.status transaction_status,
                    p.amount payment_amount,p.status payment_status,
                    c.amount cheque_amount,c.due_date_shamsi,c.status cheque_status
                    FROM financial_postings fp
                    JOIN pending_items pi ON pi.pending_id=fp.pending_id
                    LEFT JOIN expenses e ON e.expense_id=fp.expense_id
                    LEFT JOIN transactions t ON t.transaction_id=fp.transaction_id
                    LEFT JOIN payments p ON p.payment_id=fp.payment_id
                    LEFT JOIN cheques c ON c.cheque_id=fp.cheque_id
                    {where}
                    ORDER BY fp.created_at DESC LIMIT ?""",
                (int(limit),),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                payload = json.loads(d.pop('payload_json') or '{}')
            except Exception:
                payload = {}
            d['payload'] = payload
            d['display_amount'] = int(
                d.get('expense_amount') or d.get('transaction_amount') or d.get('cheque_amount') or 0
            )
            d['description'] = str(
                d.get('expense_description') or d.get('transaction_description') or payload.get('description') or ''
            )
            out.append(d)
        return out

    # ---------- GUI edits / deletes ----------
    def edit_posting(self, pending_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        old_payload = dict(item['payload'])
        new_payload = normalize_financial_edit(old_payload, changes)
        if str(new_payload.get('detected_type') or '').upper() != str(old_payload.get('detected_type') or '').upper():
            raise ValueError('تغییر نوع اصلی ثبت از GUI مجاز نیست؛ ثبت قبلی را حذف و مورد صحیح را جدا ثبت کنید.')
        self.db.begin_posting_revision(
            pending_id=pending_id, new_payload=new_payload, source='GUI_EDIT', actor_id='GUI'
        )
        try:
            refreshed = self.db.get_pending_item(pending_id)
            tg = self.db.get_telegram_message(refreshed['telegram_chat_id'], refreshed['telegram_message_id']) if refreshed else None
            if not refreshed or not tg:
                raise ValueError('پیام تلگرام لینک‌شده برای این ثبت پیدا نشد.')
            plan = build_posting_plan(
                payload=refreshed['payload'],
                raw_text=tg.get('raw_text') or '',
                telegram_message_date=tg.get('message_date') or '',
            )
            return self.db.revise_financial_posting(
                pending_id=pending_id, plan=plan, source='GUI_EDIT', actor_id='GUI'
            )
        except Exception:
            try:
                if self.db.get_open_revision(pending_id):
                    self.db.reject_posting_revision(pending_id=pending_id, source='GUI_EDIT_ROLLBACK', actor_id='GUI')
            except Exception:
                pass
            raise

    def delete_posting(self, pending_id: str, reason: str = 'حذف از GUI') -> dict[str, Any]:
        return self.db.delete_financial_posting(
            pending_id=pending_id, source='GUI', actor_id='GUI', reason=reason
        )

    def posting_telegram_target(self, pending_id: str) -> Optional[tuple[int, int]]:
        item = self.db.get_pending_item(pending_id)
        if not item:
            return None
        return int(item['telegram_chat_id']), int(item['telegram_message_id'])

    def repair_ledger(self) -> dict[str, Any]:
        return self.db.repair_paid_expense_invariants(source='GUI_REPAIR', actor_id='GUI')
