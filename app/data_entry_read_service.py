"""Read-only data-entry counters shared by the Tk toolbar and web UI."""
from __future__ import annotations

from typing import Iterable


REVIEW_STATUSES = ('PENDING_REVIEW', 'NEEDS_REVIEW', 'EDIT_PENDING')


def pending_counts(db, hidden_ids: Iterable[str] | None = None) -> dict[str, int]:
    """Count pending items using the same hidden-review rule in both UIs.

    Tk supplies ``RichBudget.hidden_review_ids()`` to preserve its existing
    route. The web UI omits ``hidden_ids`` and reads the hidden-review table
    from its private database snapshot. A database without that optional
    table counts every item, matching the web UI's previous behaviour.
    """
    with db.read() as con:
        if hidden_ids is None:
            has_hidden = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='rich_ui_hidden_reviews'"
            ).fetchone()
            where = (
                'WHERE pending_id NOT IN '
                '(SELECT pending_id FROM rich_ui_hidden_reviews WHERE hidden=1)'
                if has_hidden else ''
            )
            rows = con.execute(
                f'SELECT status, COUNT(*) c FROM pending_items {where} GROUP BY status'
            ).fetchall()
        else:
            hidden = tuple(hidden_ids)
            if hidden:
                placeholders = ','.join('?' for _ in hidden)
                rows = con.execute(
                    f'SELECT status, COUNT(*) c FROM pending_items '
                    f'WHERE pending_id NOT IN ({placeholders}) GROUP BY status',
                    hidden,
                ).fetchall()
            else:
                rows = con.execute(
                    'SELECT status, COUNT(*) c FROM pending_items GROUP BY status'
                ).fetchall()
    counts = {str(row['status']): int(row['c']) for row in rows}
    return {
        'total': sum(counts.values()),
        'review': sum(counts.get(status, 0) for status in REVIEW_STATUSES),
        'approved': counts.get('APPROVED', 0),
        'rejected': counts.get('REJECTED', 0),
    }


def hidden_count(db, hidden_ids: Iterable[str] | None = None) -> int:
    """Rows cleared from the Data Entry table with «حذف» and kept in the database: the «پنهان‌شده»
    category. They are in none of the counters of pending_counts()."""
    with db.read() as con:
        # a record deleted completely (lifecycle state PURGED) is in no category
        lifecycle = ("AND NOT EXISTS (SELECT 1 FROM transaction_lifecycle lc WHERE lc.pending_id=p.pending_id AND lc.state='PURGED')"
                     if con.execute("SELECT 1 FROM sqlite_master WHERE name='transaction_lifecycle'").fetchone() else '')
        if hidden_ids is None:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rich_ui_hidden_reviews'").fetchone():
                return 0
            return int(con.execute(
                'SELECT COUNT(*) FROM pending_items p WHERE p.pending_id IN '
                f'(SELECT pending_id FROM rich_ui_hidden_reviews WHERE hidden=1) {lifecycle}').fetchone()[0])
        hidden = tuple(hidden_ids)
        if not hidden:
            return 0
        marks = ','.join('?' for _ in hidden)
        return int(con.execute(f'SELECT COUNT(*) FROM pending_items p WHERE p.pending_id IN ({marks}) {lifecycle}', hidden).fetchone()[0])
