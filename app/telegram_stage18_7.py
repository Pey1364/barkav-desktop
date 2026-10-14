from __future__ import annotations

from datetime import datetime
import json
import os
import re
from pathlib import Path

from instance_guard_v185 import ProjectInstanceGuard


BASE_DIR = Path(__file__).resolve().parent


def _safe_project_id() -> str:
    import re
    raw = os.getenv('PEYMAAN_ACTIVE_PROJECT_ID', '')
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', raw.strip())[:80] or 'default'


def _write_status(path: Path, state: str, error_type: str = '') -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(json.dumps({
            'state': state,
            'timestamp': datetime.now().isoformat(timespec='seconds'),
            'error_type': error_type,
        }, ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)
    except Exception:
        pass


def _token_shape_is_valid(token: str) -> bool:
    """Reject empty/example tokens before any Telegram connection is opened."""
    value = str(token or '').strip()
    return bool(re.fullmatch(r'\d{6,}:[A-Za-z0-9_-]{20,}', value)) and 'token' not in value.lower()


def _validate_token_before_polling(token: str) -> None:
    """Validate the token with Telegram before constructing the polling app.

    The validation call is deliberately separate from ``run_polling`` so an
    InvalidToken or network failure never leaves a half-started poller behind.
    """
    if not _token_shape_is_valid(token):
        raise ValueError('InvalidToken')
    from telegram import Bot
    from telegram.error import InvalidToken
    from telegram.request import HTTPXRequest
    from telegram_resilience import (
        CONNECT_TIMEOUT, READ_TIMEOUT, WRITE_TIMEOUT, POOL_TIMEOUT,
    )

    async def check() -> None:
        # Bot.__init__() itself takes no *_timeout kwargs on the installed
        # python-telegram-bot version - they belong on the Request object
        # (same split telegram_stage15.py's ApplicationBuilder chain uses).
        request = HTTPXRequest(
            connect_timeout=CONNECT_TIMEOUT,
            read_timeout=READ_TIMEOUT,
            write_timeout=WRITE_TIMEOUT,
            pool_timeout=POOL_TIMEOUT,
        )
        async with Bot(token=token, request=request) as bot:
            await bot.get_me()

    try:
        import asyncio
        asyncio.run(check())
    except InvalidToken:
        raise ValueError('InvalidToken') from None


def main() -> None:
    project_id = _safe_project_id()
    runtime = BASE_DIR / 'runtime'
    status_file = runtime / f'telegram_bot_status_{project_id}.json'
    ready_file = runtime / f'telegram_bot_ready_{project_id}.flag'
    inbound_file = runtime / f'telegram_inbound_last_{project_id}.json'
    receipt_error_file = runtime / f'telegram_receipt_last_error_{project_id}.json'
    # Keep the Telegram poller lock separate from the dashboard/project lock.
    guard = ProjectInstanceGuard(runtime, f'bot_{project_id}')
    if not guard.acquire():
        _write_status(status_file, 'ERROR', 'DuplicateInstance')
        return
    _write_status(status_file, 'STARTING')
    try:
        import telegram_stage15 as legacy
        try:
            _validate_token_before_polling(legacy.CONFIG.telegram_bot_token)
        except ValueError as exc:
            _write_status(status_file, 'ERROR', str(exc) or 'InvalidToken')
            return
        except Exception as exc:
            # A network failure is also a failed preflight: do not start the
            # real poller until the same token can be validated successfully.
            _write_status(status_file, 'ERROR', type(exc).__name__)
            return
        legacy.BOT_READY_FILE = ready_file
        legacy.INBOUND_HEARTBEAT_FILE = inbound_file
        legacy.RECEIPT_ERROR_FILE = receipt_error_file
        legacy_post_init = legacy.post_init
        legacy_post_shutdown = legacy.post_shutdown

        async def post_init_with_status(application):
            try:
                await legacy_post_init(application)
            except Exception as exc:
                _write_status(status_file, 'ERROR', type(exc).__name__)
                raise
            _write_status(status_file, 'READY')

        async def post_shutdown_with_status(application):
            try:
                await legacy_post_shutdown(application)
            finally:
                _write_status(status_file, 'STOPPED')

        # ``legacy.main`` resolves these callbacks from its own module globals.
        # Wrapping them here keeps its runtime signal in the active project's
        # files, avoiding a GUI switch between an old and a scoped status.
        legacy.post_init = post_init_with_status
        legacy.post_shutdown = post_shutdown_with_status
        try:
            # loan-instalment receipts become Data Entry records with their receipt (not the Stage 9 guided flow)
            import telegram_loan_installments187 as loan_installments
            loan_installments.install(legacy)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('loan instalment handling was not installed')
        legacy.main()
    except Exception as exc:
        _write_status(status_file, 'ERROR', type(exc).__name__)
        raise
    finally:
        if not ready_file.exists():
            current = 'STOPPED'
            try:
                old = json.loads(status_file.read_text(encoding='utf-8'))
                if str(old.get('state') or '').upper() == 'ERROR':
                    current = 'ERROR'
            except Exception:
                pass
            if current != 'ERROR':
                _write_status(status_file, current)
        guard.release()


if __name__ == '__main__':
    main()
