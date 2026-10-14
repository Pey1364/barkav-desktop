# Peymaan V2 Stage 9.1 — Telegram Network Resilience

This patch does not change financial/database logic.

- Larger Telegram request and polling timeouts
- Explicit HTTP/1.1
- Larger connection pool
- Infinite bootstrap retries for temporary startup outages
- PTB transient TimedOut/NetworkError tracebacks collapsed to a rate-limited one-line warning
- Existing application error handlers remain active
- Added `network_diagnostic.py`

If recurring network problems persist, use Python 3.13 for production because PTB currently does not officially support Python 3.14.
