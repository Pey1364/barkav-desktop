from __future__ import annotations

import json
import os
import importlib.util
from pathlib import Path
from typing import Any


def read_secrets(base_dir: str | Path) -> dict[str, Any]:
    base = Path(base_dir)
    p = base / 'secrets.local.json'
    if not p.exists():
        p = base.parent / 'data' / 'secrets.local.json'
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def preflight_snapshot(base_dir: str | Path) -> dict[str, Any]:
    base = Path(base_dir)
    secrets = read_secrets(base)
    data = base / 'data'
    db_env = os.getenv('STAGE4_DB_PATH', '').strip()
    db = Path(db_env) if db_env else data / 'stage4_test.sqlite3'
    if db_env and not db.is_absolute():
        db = base / db
    def has_module(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except Exception:
            return False
    secret_path = base / 'secrets.local.json'
    if not secret_path.exists():
        secret_path = base.parent / 'data' / 'secrets.local.json'
    return {
        'secrets_exists': secret_path.exists(),
        'data_exists': data.exists(),
        'db_path': str(db),
        'db_exists': db.exists(),
        'bot_token': bool(str(os.getenv('TELEGRAM_BOT_TOKEN') or secrets.get('TELEGRAM_BOT_TOKEN') or '').strip()),
        'gemini_key': bool(str(os.getenv('GEMINI_API_KEY') or secrets.get('GEMINI_API_KEY') or '').strip()),
        'gemini_sdk': has_module('google.genai'),
        'telegram_sdk': has_module('telegram'),
        'pil_sdk': has_module('PIL'),
        'jdatetime_sdk': has_module('jdatetime'),
        'admin_id': str(os.getenv('ADMIN_USER_ID') or secrets.get('ADMIN_USER_ID') or '').strip(),
        'group_id': str(os.getenv('GROUP_CHAT_ID') or secrets.get('GROUP_CHAT_ID') or '').strip(),
        'gemini_model': str(os.getenv('GEMINI_MODEL') or secrets.get('GEMINI_MODEL') or 'gemini-flash-latest').strip(),
        'test_tag_required': str(os.getenv('STAGE4_REQUIRE_TEST_TAG', 'false')).lower() in {'1','true','yes','on'},
    }


def tail(path: str | Path, lines: int = 80) -> str:
    p = Path(path)
    if not p.exists():
        return 'لاگ هنوز ساخته نشده است.'
    try:
        text = p.read_text(encoding='utf-8', errors='replace').splitlines()
        return '\n'.join(text[-lines:])
    except Exception as exc:
        return f'خواندن لاگ ناموفق: {exc}'
