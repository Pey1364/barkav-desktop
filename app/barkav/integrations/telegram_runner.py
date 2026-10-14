from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]


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


def main() -> None:
    project_id = _safe_project_id()
    runtime = BASE_DIR / 'runtime'
    status_file = runtime / f'telegram_bot_status_{project_id}.json'
    ready_file = runtime / f'telegram_bot_ready_{project_id}.flag'
    inbound_file = runtime / f'telegram_inbound_last_{project_id}.json'
    receipt_error_file = runtime / f'telegram_receipt_last_error_{project_id}.json'
    _write_status(status_file, 'STARTING')
    try:
        import telegram_bot as legacy
        legacy.BOT_READY_FILE = ready_file
        legacy.INBOUND_HEARTBEAT_FILE = inbound_file
        legacy.RECEIPT_ERROR_FILE = receipt_error_file
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


if __name__ == '__main__':
    main()
