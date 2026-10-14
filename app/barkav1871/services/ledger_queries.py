"""Read-only ledger projections used by canonical tables and reports."""

from __future__ import annotations

from typing import Any

from .finance import FinanceDB


class LedgerQueryService:
    def __init__(self, db: FinanceDB):
        self.db = db

    def list_transactions(self, *, direction: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        clauses = ["status = 'POSTED'", "deleted_at IS NULL"]
        params: list[Any] = []
        if direction in {"IN", "OUT"}:
            clauses.append("direction = ?")
            params.append(direction)
        params.append(max(1, min(int(limit), 2_000)))
        sql = """
            SELECT transaction_id, event_date, shamsi_date, direction, amount, category,
                   payer_name, receiver_name, description, source_type, sale_id, loan_id
              FROM transactions
             WHERE """ + " AND ".join(clauses) + " ORDER BY event_date DESC, created_at DESC LIMIT ?"
        with self.db.read() as connection:
            return [dict(row) for row in connection.execute(sql, params).fetchall()]

    def list_expenses(self, *, limit: int = 500) -> list[dict[str, Any]]:
        with self.db.read() as connection:
            rows = connection.execute(
                """SELECT expense_id, event_date, shamsi_date, vendor_name, description,
                          category, final_amount, status
                     FROM expenses WHERE deleted_at IS NULL
                     ORDER BY event_date DESC, created_at DESC LIMIT ?""",
                (max(1, min(int(limit), 2_000)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_cheques(self, *, limit: int = 500) -> list[dict[str, Any]]:
        """Return cheque lifecycle data without advancing or changing its status."""
        with self.db.read() as connection:
            rows = connection.execute(
                """SELECT cheque_id, amount, issue_date, issue_date_shamsi, due_date,
                          due_date_shamsi, cheque_serial, issuer_bank, receiver_name,
                          description, status, is_guarantee, guarantee_status
                     FROM cheques
                    ORDER BY due_date ASC, created_at ASC LIMIT ?""",
                (max(1, min(int(limit), 2_000)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_loans(self, *, limit: int = 500) -> list[dict[str, Any]]:
        """Return loan summaries without the service-side status refresh."""
        with self.db.read() as connection:
            rows = connection.execute(
                """SELECT loan_id, lender_name, loan_type, principal_amount,
                          net_received_amount, total_repayment, received_date_shamsi,
                          installment_count, status, description,
                          COALESCE((SELECT SUM(paid_amount) FROM loan_installments li
                                    WHERE li.loan_id = loans.loan_id
                                      AND li.status != 'CANCELLED'), 0) AS paid_total,
                          (SELECT due_date_shamsi FROM loan_installments li
                            WHERE li.loan_id = loans.loan_id
                              AND li.status NOT IN ('PAID', 'CANCELLED')
                            ORDER BY due_date LIMIT 1) AS next_due_shamsi
                     FROM loans
                    WHERE status != 'CANCELLED'
                    ORDER BY COALESCE(received_date, '') DESC, loan_id DESC LIMIT ?""",
                (max(1, min(int(limit), 2_000)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_documents(self, *, limit: int = 500) -> list[dict[str, Any]]:
        """Return registered project documents; file access remains an explicit action."""
        with self.db.read() as connection:
            rows = connection.execute(
                """SELECT document_id, document_type, title, local_path, notes, created_at
                     FROM project_documents
                    WHERE deleted_at IS NULL
                    ORDER BY created_at DESC LIMIT ?""",
                (max(1, min(int(limit), 2_000)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_manager_withdrawals(self, *, limit: int = 500) -> list[dict[str, Any]]:
        """Return posted manager-account withdrawals as an auditable read-only list."""
        with self.db.read() as connection:
            rows = connection.execute(
                """SELECT transaction_id, event_date, shamsi_date, amount, receiver_name,
                          description, source_type
                     FROM transactions
                    WHERE status = 'POSTED' AND deleted_at IS NULL
                      AND direction = 'OUT' AND category = 'CONTRACTOR_FEE'
                    ORDER BY event_date DESC, created_at DESC LIMIT ?""",
                (max(1, min(int(limit), 2_000)),),
            ).fetchall()
        return [dict(row) for row in rows]
