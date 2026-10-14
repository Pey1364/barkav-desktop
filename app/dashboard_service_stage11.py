from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dashboard_service_stage9 import DashboardServiceStage9
from finance_db import FinanceDB
from revenue_service import gregorian_to_shamsi, shamsi_to_gregorian


@dataclass(frozen=True)
class ManagerSummary:
    signed_days: int
    signed_average: int
    toman_month: int
    manager_fee: int
    withdrawals_signed: int
    balance: int


class DashboardServiceStage11(DashboardServiceStage9):
    """Stage 11 dashboard/read-model helpers.

    All values are derived from SQLite; no aggregate is persisted here.
    The 30-day window is inclusive of today and day +30.
    """

    def __init__(self, db: FinanceDB, base_dir: str | Path):
        super().__init__(db, base_dir)

    def financial_flow_totals(self) -> dict[str, int]:
        with self.db.read() as con:
            row=con.execute("""SELECT
                COALESCE(SUM(CASE WHEN direction='IN' THEN amount ELSE 0 END),0) total_in,
                COALESCE(SUM(CASE WHEN direction='OUT' THEN amount ELSE 0 END),0) total_out
                FROM transactions WHERE status='POSTED' AND deleted_at IS NULL""").fetchone()
        return {'total_in':int(row['total_in'] or 0),'total_out':int(row['total_out'] or 0)}

    def manager_summary_shamsi(self, start_shamsi: str, end_shamsi: str) -> ManagerSummary:
        # Use the exposure engine even when there has never been a withdrawal.
        # The fee accrual itself creates positive manager exposure.
        start=shamsi_to_gregorian(start_shamsi)
        end=shamsi_to_gregorian(end_shamsi)
        exp=self.db.manager_exposure(start,end)
        fee=self.db.manager_fee_accrued()
        withdrawals=self.db.manager_withdrawals()
        active=int(exp.creditor_days)+int(exp.debtor_days)
        signed_days=int(exp.creditor_days)-int(exp.debtor_days)
        signed_average=round(int(exp.net_toman_days)/active) if active else 0
        toman_month=round(int(exp.net_toman_days)/30)
        return ManagerSummary(
            signed_days=signed_days,
            signed_average=signed_average,
            toman_month=toman_month,
            manager_fee=int(fee),
            withdrawals_signed=-int(withdrawals),
            balance=int(fee)-int(withdrawals),
        )

    @staticmethod
    def _window(days: int=30) -> tuple[date,date]:
        today=date.today(); return today,today+timedelta(days=max(0,int(days)))

    def upcoming_cheques(self, days: int=30) -> list[dict[str,Any]]:
        start,end=self._window(days)
        with self.db.read() as con:
            rows=con.execute("""SELECT c.*,e.description expense_description
                FROM cheques c LEFT JOIN expenses e ON e.expense_id=c.expense_id
                WHERE c.status IN ('ISSUED','PENDING_DUE','RETURNED')
                  AND c.due_date>=? AND c.due_date<=?
                ORDER BY c.due_date,c.amount DESC""",(start.isoformat(),end.isoformat())).fetchall()
        out=[]
        for r in rows:
            d=dict(r); due=date.fromisoformat(d['due_date']); d['days_to_due']=(due-start).days
            d['_sum_amount']=int(d.get('amount') or 0); out.append(d)
        return out

    def cheque_30d_summary(self, days: int=30) -> dict[str,Any]:
        rows=self.upcoming_cheques(days); amount=sum(int(r.get('amount') or 0) for r in rows); cash=self.db.cash_balance()
        return {'rows':rows,'count':len(rows),'amount':amount,'cash':cash,'surplus':cash-amount}

    def upcoming_buyer_installments(self, days: int=30) -> list[dict[str,Any]]:
        self.revenue.refresh_installment_statuses()
        start,end=self._window(days)
        with self.db.read() as con:
            rows=con.execute("""SELECT i.*,s.buyer_name,s.buyer_phone,s.sale_id,u.unit_number,u.display_unit_id
                FROM installments i JOIN sales s ON s.sale_id=i.sale_id JOIN units u ON u.unit_id=s.unit_id
                WHERE s.status!='CANCELLED' AND i.status!='CANCELLED' AND i.paid_amount<i.amount
                  AND i.due_date>=? AND i.due_date<=?
                ORDER BY i.due_date,s.buyer_name""",(start.isoformat(),end.isoformat())).fetchall()
        out=[]
        for r in rows:
            d=dict(r); d['outstanding']=max(0,int(d.get('amount') or 0)-int(d.get('paid_amount') or 0)); d['days_to_due']=(date.fromisoformat(d['due_date'])-start).days; d['_sum_amount']=d['outstanding']; out.append(d)
        return out

    def overdue_buyer_installments(self) -> list[dict[str,Any]]:
        self.revenue.refresh_installment_statuses()
        today=date.today()
        with self.db.read() as con:
            rows=con.execute("""SELECT i.*,s.buyer_name,s.buyer_phone,s.sale_id,u.unit_number,u.display_unit_id
                FROM installments i JOIN sales s ON s.sale_id=i.sale_id JOIN units u ON u.unit_id=s.unit_id
                WHERE s.status!='CANCELLED' AND i.status!='CANCELLED' AND i.paid_amount<i.amount AND i.due_date<?
                ORDER BY i.due_date,s.buyer_name""",(today.isoformat(),)).fetchall()
        out=[]
        for r in rows:
            d=dict(r); d['outstanding']=max(0,int(d.get('amount') or 0)-int(d.get('paid_amount') or 0)); d['days_overdue']=(today-date.fromisoformat(d['due_date'])).days; d['_sum_amount']=d['outstanding']; out.append(d)
        return out

    def sales_30d_summary(self, days: int=30) -> dict[str,Any]:
        base=self.revenue.buyer_dashboard(); upcoming=self.upcoming_buyer_installments(days); overdue=self.overdue_buyer_installments()
        return {
            'contract_sales':int(base['contract_sales']),
            'cash_received':int(base['cash_received']),
            'receivable':int(base['receivable']),
            'upcoming_amount':sum(int(r['outstanding']) for r in upcoming),
            'overdue_amount':sum(int(r['outstanding']) for r in overdue),
            'upcoming_rows':upcoming,
            'overdue_rows':overdue,
        }

    def upcoming_loan_installments(self, days: int=30) -> list[dict[str,Any]]:
        # Refresh statuses through list_loans before querying.
        self.loans.list_loans()
        start,end=self._window(days)
        with self.db.read() as con:
            rows=con.execute("""SELECT li.*,l.lender_name,l.contract_number,l.loan_type
                FROM loan_installments li JOIN loans l ON l.loan_id=li.loan_id
                WHERE l.status='ACTIVE' AND li.status!='CANCELLED' AND li.paid_amount<li.amount
                  AND li.due_date>=? AND li.due_date<=?
                ORDER BY li.due_date,l.lender_name,li.installment_number""",(start.isoformat(),end.isoformat())).fetchall()
        out=[]
        for r in rows:
            d=dict(r); d['outstanding']=max(0,int(d.get('amount') or 0)-int(d.get('paid_amount') or 0)); d['days_to_due']=(date.fromisoformat(d['due_date'])-start).days; d['_sum_amount']=d['outstanding']; out.append(d)
        return out

    def loans_30d_summary(self, days: int=30) -> dict[str,Any]:
        totals=self.loans.loan_totals(); rows=self.upcoming_loan_installments(days)
        return {**totals,'upcoming_amount':sum(int(r['outstanding']) for r in rows),'upcoming_rows':rows}

    def liquidity_30d_summary(self, days: int=30) -> dict[str,int]:
        cash=self.db.cash_balance(); ch=self.cheque_30d_summary(days); sales=self.sales_30d_summary(days); loans=self.loans_30d_summary(days)
        obligations=int(ch['amount'])+int(loans['upcoming_amount'])
        expected=int(sales['upcoming_amount'])
        return {
            'cash':int(cash),
            'cheques':int(ch['amount']),
            'loan_installments':int(loans['upcoming_amount']),
            'obligations':obligations,
            'expected_inflows':expected,
            'conservative_balance':int(cash)-obligations,
            'projected_balance':int(cash)+expected-obligations,
        }
