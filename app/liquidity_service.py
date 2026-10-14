"""۳۰ روز آینده: the dashboard's 30-day liquidity, independent of Tk.

Moved unchanged out of dashboard_stage18_7.py (``contractor_commitments_30d_187``,
``thirty_day_liquidity_breakdown_187``, ``Stage187Dashboard._issued_cheques_by_contract_187``
and ``_thirty_day_summary_187``) so the Tk window and the pywebview bridge
read one implementation.  This module imports no UI code.

Contract
--------
``thirty_day_summary(service, contracts, *, db=None, today=None, days=30,
to_gregorian=shamsi_to_gregorian, cheque=None, loans=None, sales=None) -> dict``

* ``service``: a ``dashboard_read_model.DashboardServiceStage12`` (only
  ``cheque_30d_summary``, ``loans_30d_summary``, ``sales_30d_summary`` and
  ``db`` are used).
* ``contracts``: the contractor contracts list, as
  ``contractor_store_stage18_7.load_contracts()`` returns it.  Passed in, not
  loaded here, because that store resolves its file from ``STAGE4_DB_PATH``.
* ``db``: the ``FinanceDB`` to read postings and cash from; defaults to
  ``service.db``.
* ``cheque``/``loans``/``sales``: optional, already-read results of
  ``service.cheque_30d_summary(days)`` / ``loans_30d_summary`` /
  ``sales_30d_summary``; read here when omitted.
* Returns ints in toman: ``claims``, ``commitments``, ``cheques``,
  ``installments``, ``balance`` (claims - commitments - cheques -
  installments), ``cash``, ``liquidity_needed`` (cash + balance), plus
  ``commitment_rows`` (``contract_id``, ``contract_title``, ``label``,
  ``due_date`` as ``datetime.date``, ``amount``), and separately
  ``overdue_commitments`` / ``overdue_rows`` (same row shape plus
  ``days_overdue``): schedule amounts due before ``today`` and still unpaid.
  Overdue amounts are NOT included in ``balance`` or ``liquidity_needed``.
* Reads only; never writes.

Due dates: ``revenue_service.shamsi_to_gregorian`` returns an ISO *string*;
the loop used to accept only ``date``/``datetime``, so every milestone was
skipped and ``commitments`` was always 0 (docs/LIQUIDITY_SERVICE_19_1_1.md).
ISO strings are now parsed as dates too.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable

from contractor_store_stage18_7 import paid_total
from revenue_service import shamsi_to_gregorian

# Same digit table and cleaning as ui_stage18_3.parse_int, which the Tk code
# used; that module imports tkinter, so its behaviour is reproduced here and
# pinned by tests/test_liquidity_service.py against the original.
_EN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def parse_amount(value: Any, default: int = 0) -> int:
    text = str(value if value is not None else '').translate(_EN_DIGITS)
    text = text.replace(',', '').replace('٬', '').replace('،', '').strip()
    text = re.sub(r'[^0-9\-]', '', text)
    if text in ('', '-'):
        return default
    try:
        return int(text)
    except ValueError:
        return default


def contractor_schedule_due(
    contracts: Iterable[dict] | None, start: date, end: date,
    issued_by_contract: dict[str, int] | None = None,
    *, to_gregorian: Callable[[str], Any] = shamsi_to_gregorian,
) -> dict[str, Any]:
    """Unpaid contractor schedule amounts, split into in-window and overdue.

    One pass per contract, so a milestone lands in at most one list:

    * Confirmed payments settle the oldest milestone first (overdue ones
      included), exactly as before.
    * ``window`` = milestones due in ``[start, end]``. An issued cheque for
      the contract reserves their remaining amount first, so it stays in the
      cheque total and is not shown twice as a contractor obligation. This
      is the figure the ۳۰ روز آینده card has always used.
    * ``overdue`` = milestones due before ``start`` still unpaid. Only cheque
      amount left over after the window is applied to them, so the window
      figure is unchanged and no cheque is counted twice. They are reported
      separately and are not part of the 30-day balance.

    Returns ``{'window_total', 'window_rows', 'overdue_total', 'overdue_rows'}``.
    """
    issued_by_contract = issued_by_contract or {}
    window_total = overdue_total = 0
    window_rows: list[dict] = []
    overdue_rows: list[dict] = []
    for contract in contracts or []:
        contract_id = str(contract.get('contract_id') or '').strip()
        if not contract_id:
            continue
        title = str(contract.get('title') or contract_id)
        milestones = []
        for item in contract.get('payment_schedule') or []:
            raw_date = str(item.get('due_date_shamsi') or '').strip()
            try:
                due = to_gregorian(raw_date)
            except (TypeError, ValueError):
                continue
            if isinstance(due, datetime):
                due = due.date()
            elif isinstance(due, str):
                # What revenue_service.shamsi_to_gregorian actually returns.
                try:
                    due = date.fromisoformat(due.strip())
                except ValueError:
                    continue
            if not isinstance(due, date):
                continue
            amount = parse_amount(item.get('amount') or 0)
            if amount > 0:
                milestones.append((due, amount, str(item.get('label') or 'مرحله پرداخت')))
        milestones.sort(key=lambda item: item[0])
        settled = max(0, int(paid_total(contract)))
        issued = max(0, int(issued_by_contract.get(contract_id) or 0))
        overdue_candidates = []
        for due, amount, label in milestones:
            paid = min(settled, amount)
            settled -= paid
            outstanding = amount - paid
            if start <= due <= end and outstanding:
                covered_by_cheque = min(issued, outstanding)
                issued -= covered_by_cheque
                due_without_cheque = outstanding - covered_by_cheque
                if due_without_cheque:
                    window_total += due_without_cheque
                    window_rows.append({
                        'contract_id': contract_id,
                        'contract_title': title,
                        'label': label,
                        'due_date': due,
                        'amount': due_without_cheque,
                    })
            elif due < start and outstanding:
                overdue_candidates.append((due, outstanding, label))
        for due, outstanding, label in overdue_candidates:
            covered_by_cheque = min(issued, outstanding)
            issued -= covered_by_cheque
            unpaid = outstanding - covered_by_cheque
            if unpaid:
                overdue_total += unpaid
                overdue_rows.append({
                    'contract_id': contract_id,
                    'contract_title': title,
                    'label': label,
                    'due_date': due,
                    'amount': unpaid,
                    'days_overdue': (start - due).days,
                })
    return {'window_total': window_total, 'window_rows': window_rows,
            'overdue_total': overdue_total, 'overdue_rows': overdue_rows}


def contractor_commitments_30d(
    contracts: Iterable[dict] | None, start: date, end: date,
    issued_by_contract: dict[str, int] | None = None,
    *, to_gregorian: Callable[[str], Any] = shamsi_to_gregorian,
) -> tuple[int, list[dict]]:
    """Return due contractor schedule amounts in ``[start, end]`` not already chequed."""
    due = contractor_schedule_due(contracts, start, end, issued_by_contract, to_gregorian=to_gregorian)
    return due['window_total'], due['window_rows']


def thirty_day_liquidity_breakdown(*, claims: int, commitments: int,
                                   cheques: int, installments: int,
                                   cash: int) -> dict[str, int]:
    """Calculate 30-day claims, obligations, cash, and liquidity."""
    claims = max(0, int(claims or 0))
    commitments = max(0, int(commitments or 0))
    cheques = max(0, int(cheques or 0))
    installments = max(0, int(installments or 0))
    cash = int(cash or 0)
    balance = claims - commitments - cheques - installments
    return {
        'claims': claims,
        'commitments': commitments,
        'cheques': cheques,
        'installments': installments,
        'balance': balance,
        'cash': cash,
        'liquidity_needed': cash + balance,
    }


def issued_cheques_by_contract(db, cheque_rows: Iterable[dict]) -> dict[str, int]:
    """Map upcoming issued cheques to their approval payload's contract."""
    cheque_rows = list(cheque_rows or [])
    expense_ids = sorted({str(row.get('expense_id') or '').strip() for row in cheque_rows
                          if str(row.get('expense_id') or '').strip()})
    if not expense_ids:
        return {}
    try:
        placeholders = ','.join('?' for _ in expense_ids)
        with db.read() as con:
            postings = con.execute(
                f'SELECT expense_id, pending_id FROM financial_postings '
                f'WHERE expense_id IN ({placeholders})', expense_ids,
            ).fetchall()
    except sqlite3.Error:
        return {}
    by_expense = {str(row['expense_id']): str(row['pending_id']) for row in postings}
    totals: dict[str, int] = {}
    for cheque in cheque_rows:
        pending_id = by_expense.get(str(cheque.get('expense_id') or ''))
        if not pending_id:
            continue
        try:
            pending = db.get_pending_item(pending_id) or {}
            contract_id = str((pending.get('payload') or {}).get('contract_id') or '').strip()
        except (sqlite3.Error, TypeError, ValueError):
            continue
        if contract_id:
            totals[contract_id] = totals.get(contract_id, 0) + int(cheque.get('amount') or 0)
    return totals


def thirty_day_summary(service, contracts: Iterable[dict] | None, *, db=None,
                       today: date | None = None, days: int = 30,
                       to_gregorian: Callable[[str], Any] = shamsi_to_gregorian,
                       cheque: dict | None = None, loans: dict | None = None,
                       sales: dict | None = None) -> dict[str, Any]:
    """The five cash commitments shown on the ۳۰ روز آینده card and dialog.

    ``cheque``/``loans``/``sales`` accept results the caller already read
    with the same ``days`` (``service.cheque_30d_summary(days)`` etc.), so a
    caller that shows those cards too does not run the queries twice.
    """
    db = db if db is not None else service.db
    start = today or date.today()
    end = start + timedelta(days=days)
    cheque = cheque if cheque is not None else service.cheque_30d_summary(days)
    loans = loans if loans is not None else service.loans_30d_summary(days)
    sales = sales if sales is not None else service.sales_30d_summary(days)
    issued = issued_cheques_by_contract(db, cheque.get('rows') or [])
    due = contractor_schedule_due(contracts, start, end, issued, to_gregorian=to_gregorian)
    commitments, commitment_rows = due['window_total'], due['window_rows']
    cash = int(db.cash_balance())
    cheques = int(cheque.get('amount') or 0)
    installments = int(loans.get('upcoming_amount') or 0)
    claims = int(sales.get('upcoming_amount') or 0)
    return {
        **thirty_day_liquidity_breakdown(
            claims=claims,
            commitments=commitments,
            cheques=cheques,
            installments=installments,
            cash=cash,
        ),
        'commitment_rows': commitment_rows,
        # Shown separately as تعهدات معوق; not part of balance/liquidity_needed.
        'overdue_commitments': due['overdue_total'],
        'overdue_rows': due['overdue_rows'],
    }
