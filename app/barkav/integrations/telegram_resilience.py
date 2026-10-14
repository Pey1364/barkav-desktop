from __future__ import annotations

import logging
import threading
import time

from telegram.error import NetworkError, TimedOut

# Conservative settings for unstable/filtered networks.
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 60
WRITE_TIMEOUT = 60
POOL_TIMEOUT = 30
GET_UPDATES_CONNECT_TIMEOUT = 30
GET_UPDATES_READ_TIMEOUT = 90
GET_UPDATES_WRITE_TIMEOUT = 60
GET_UPDATES_POOL_TIMEOUT = 30
CONNECTION_POOL_SIZE = 32
GET_UPDATES_CONNECTION_POOL_SIZE = 2
POLLING_TIMEOUT = 30


class _TelegramTransientNetworkFilter(logging.Filter):
    """Collapse expected transient PTB network tracebacks to a rate-limited one-line warning.

    PTB already retries polling network errors. A temporary Telegram/httpx timeout should not
    look like an application crash in the console. Non-network exceptions are untouched.
    """

    _lock = threading.Lock()
    _last_notice = 0.0
    _notice_interval = 60.0

    def filter(self, record: logging.LogRecord) -> bool:
        if not record.name.startswith("telegram"):
            return True

        exc = None
        if record.exc_info:
            exc = record.exc_info[1]

        msg = record.getMessage().lower()
        is_transient = isinstance(exc, (TimedOut, NetworkError)) or (
            "timed out" in msg or "timeout" in msg or "networkerror" in msg
        )
        if not is_transient:
            return True

        now = time.monotonic()
        with self._lock:
            if now - self._last_notice < self._notice_interval:
                return False
            self.__class__._last_notice = now

        record.levelno = logging.WARNING
        record.levelname = "WARNING"
        record.msg = "Telegram network timeout; automatic retry is active."
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def configure_telegram_network_logging() -> None:
    """Install the transient-network filter once on root handlers."""
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, _TelegramTransientNetworkFilter) for f in handler.filters):
            handler.addFilter(_TelegramTransientNetworkFilter())
