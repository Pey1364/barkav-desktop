"""Which cheques still stand as a debt, and which count with the cashed ones.

The database keeps its older vocabulary in ``cheques.status`` (ISSUED, PENDING_DUE, CASHED, RETURNED,
CANCELLED); the states the screens show beyond it live in ``settlement_mode``. «عودتی به شرط تسویه» is stored
as status RETURNED with settlement_mode RETURNED_ON_SETTLEMENT: the cheque went back to its issuer because
the debt was settled another way, so nothing is owed through it any more and it counts with the cashed
cheques (the user's rule of 2026-10-06). A plain «برگشتی» cheque is still owed. A cheque replaced by a bank
transfer (RETURNED with REPLACED_BY_TRANSFER) owes nothing either, but its replacement row is the cashed
one, so it is not counted as cashed a second time.

Everything that lists, sums or filters cheques by «open» or «cashed» asks this module, so the dashboard
cards, the 30-day forecast, the calendar, the search and the cheque tab cannot disagree.
"""
from __future__ import annotations

from typing import Any, Mapping

OPEN_STATUSES = ('ISSUED', 'PENDING_DUE')
#: returned to the issuer because the debt was settled another way: nothing is owed, it counts as cashed
SETTLED_MODES = ('RETURNED_ON_SETTLEMENT',)
#: returned cheques nothing is owed through (the cashed ones among them are SETTLED_MODES only)
NO_DEBT_MODES = SETTLED_MODES + ('REPLACED_BY_TRANSFER',)


def _upper(value: Any) -> str:
    return str(value or '').strip().upper()


def is_open(row: Mapping[str, Any]) -> bool:
    """The cheque is still owed: issued, near its due date, or returned (برگشتی) and not settled."""
    status, mode = _upper(row.get('status')), _upper(row.get('settlement_mode'))
    return status in OPEN_STATUSES or (status == 'RETURNED' and mode not in NO_DEBT_MODES)


def counts_as_cashed(row: Mapping[str, Any]) -> bool:
    """The cheque is paid for good: cashed, or returned on condition of settlement."""
    status, mode = _upper(row.get('status')), _upper(row.get('settlement_mode'))
    return status == 'CASHED' or (status == 'RETURNED' and mode in SETTLED_MODES)


def open_sql(alias: str = '') -> str:
    """is_open() as a SQL condition on the cheques table, which may be aliased."""
    prefix = f'{alias}.' if alias else ''
    modes = ','.join(f"'{mode}'" for mode in NO_DEBT_MODES)
    states = ','.join(f"'{status}'" for status in OPEN_STATUSES)
    return (f"({prefix}status IN ({states}) OR "
            f"({prefix}status='RETURNED' AND COALESCE({prefix}settlement_mode,'') NOT IN ({modes})))")
