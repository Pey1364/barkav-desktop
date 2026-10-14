"""Channel-independent cheque reminder scheduler and delivery handoff."""

from __future__ import annotations

from typing import Any, Iterable

from barkav1871.services import FinanceDB


class ReminderService:
    """Keeps scheduling in SQLite; a bot/email adapter only delivers rows."""

    def __init__(self, db: FinanceDB):
        self.db = db

    def schedule_open_cheques(self, *, times: Iterable[str], days_before: int = 5) -> int:
        return self.db.ensure_all_open_cheque_reminders(
            reminder_times=times, days_before=days_before, telegram=True, email=False,
        )

    def due(self, *, now_iso: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        return self.db.get_due_cheque_reminders(now_iso, limit=limit)

    def acknowledge_delivery(self, reminder_id: str, *, channel: str, details: str = "") -> None:
        self.db.mark_reminder_sent(reminder_id, channel=channel, details=details)

    def record_delivery_failure(self, reminder_id: str, *, channel: str, details: str = "") -> None:
        self.db.log_reminder_failure(reminder_id, channel=channel, details=details)
