"""Build the read-only dashboard summary the web UI shows.

Every number comes from the existing Python services
(``dashboard_read_model.DashboardServiceStage12``); nothing is recalculated
here except plain grouping.  The result contains only JSON scalars, lists
and dicts - no dates, dataclasses, rows or file paths leave this module.

۳۰ روز آینده comes from ``liquidity_service.thirty_day_summary`` - the same
function the Tk window's ``Stage187Dashboard._thirty_day_summary_187`` now
calls - with the contracts read beside the project database
(``webui.snapshot.read_contracts_beside``), so both show the same figures.
"""
from __future__ import annotations

import dataclasses
import sqlite3
from typing import Any

import liquidity_service
import data_entry_read_service


def _scalars(values: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    out = {}
    for key in keys:
        value = values.get(key)
        out[key] = value if isinstance(value, (int, float, str, bool)) or value is None else str(value)
    return out


def pending_counts(db) -> dict[str, int]:
    """Compatibility entry point for the shared data-entry read service."""
    return data_entry_read_service.pending_counts(db)


def build_dashboard_summary(service, *, project_name: str = '',
                            contracts: list | None = None) -> dict[str, Any]:
    overview = dataclasses.asdict(service.overview())
    project = service.project.get_project() or {}
    sales = service.sales_30d_summary(30)
    loans = service.loans_30d_summary(30)
    cheques_30 = service.cheque_30d_summary(30)
    try:
        pending = pending_counts(service.db)
    except sqlite3.Error:
        pending = None
    return {
        'project': {
            'name': str(project.get('name') or project_name or ''),
            'address': str(project.get('address') or ''),
            'postal_code': str(project.get('postal_code') or ''),
            'registration_plate': str(project.get('registration_plate') or ''),
            'municipal_file_no': str(project.get('municipal_file_no') or ''),
        },
        'overview': _scalars(overview, tuple(overview)),
        'flows': _scalars(service.financial_flow_totals(), ('total_in', 'total_out')),
        'cheques': {
            'all': _scalars(service.cheque_total_summary(), ('count', 'amount')),
            'next_30d': _scalars(cheques_30, ('count', 'amount')),
        },
        'sales_30d': _scalars(sales, ('contract_sales', 'cash_received', 'receivable',
                                      'upcoming_amount', 'overdue_amount')),
        'loans_30d': _scalars(loans, ('principal', 'paid', 'remaining', 'upcoming_amount')),
        'liquidity_30d': liquidity_30d(service, contracts or [],
                                       cheque=cheques_30, loans=loans, sales=sales),
        'pending': pending,
    }


def liquidity_30d(service, contracts: list, **already_read) -> dict[str, Any]:
    """The Tk dashboard's ۳۰ روز آینده figures, as JSON.

    ``already_read`` passes the cheque/loans/sales 30-day results the summary
    has read for its own cards, so they are not queried a second time.
    """
    summary = liquidity_service.thirty_day_summary(service, contracts, **already_read)
    return {
        **_scalars(summary, ('claims', 'commitments', 'cheques', 'installments',
                             'balance', 'cash', 'liquidity_needed')),
        'commitment_rows': [
            {'contract_id': str(row['contract_id']), 'contract_title': str(row['contract_title']),
             'label': str(row['label']), 'due_date': row['due_date'].isoformat(),
             'amount': int(row['amount'])}
            for row in summary.get('commitment_rows') or []
        ],
        # تعهدات معوق: before today and unpaid; not part of balance.
        'overdue_commitments': int(summary.get('overdue_commitments') or 0),
        'overdue_rows': [
            {'contract_id': str(row['contract_id']), 'contract_title': str(row['contract_title']),
             'label': str(row['label']), 'due_date': row['due_date'].isoformat(),
             'amount': int(row['amount']), 'days_overdue': int(row['days_overdue'])}
            for row in summary.get('overdue_rows') or []
        ],
    }
