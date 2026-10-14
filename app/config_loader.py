from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from runtime_base import local_secrets_path


@dataclass(frozen=True)
class Stage4Config:
    telegram_bot_token: str
    gemini_api_key: str
    admin_user_id: int
    db_path: str
    gemini_model: str
    require_test_tag: bool
    test_tag: str
    enable_reaction_in_test: bool
    group_chat_id: Optional[int]
    # همهٔ گروه‌های مجاز این پروژه (شاملِ group_chat_id هم). وقتی این خالی
    # است یعنی هنوز هیچ گروهی تنظیم نشده - رفتار قدیمیِ یادگیری خودکار از
    # اولین پیام دست‌نخورده می‌ماند (نگاه کن به _maybe_learn_group).
    group_chat_ids: tuple[int, ...]
    sheets_enabled: bool
    spreadsheet_name: str
    google_credentials_file: str
    sheets_sync_interval_seconds: int
    sheets_sync_batch_size: int
    cheque_reminders_enabled: bool
    cheque_reminder_days_before: int
    cheque_reminder_times: tuple[str, ...]
    reminder_check_interval_seconds: int
    buyer_reminders_enabled: bool
    buyer_reminder_days_before: int
    buyer_reminder_days_after: int
    buyer_reminder_time: str


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_config(base_dir: str | Path) -> Stage4Config:
    base = Path(base_dir)
    data = {}
    local = local_secrets_path(base)
    if local is not None:
        data.update(json.loads(local.read_text(encoding="utf-8")))

    def get(name, default=None):
        return os.getenv(name, data.get(name, default))

    token = get("TELEGRAM_BOT_TOKEN")
    gemini = get("GEMINI_API_KEY")
    admin = get("ADMIN_USER_ID")
    if not token or not gemini or not admin:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN / GEMINI_API_KEY / ADMIN_USER_ID. "
            "Copy secrets.local.example.json to secrets.local.json and fill it locally."
        )

    group = get("GROUP_CHAT_ID")
    group_id = int(group) if group not in (None, "", 0, "0") else None
    groups_raw = get("GROUP_CHAT_IDS")
    if groups_raw not in (None, ""):
        group_ids = tuple(
            int(piece.strip()) for piece in str(groups_raw).split(",") if piece.strip() not in ("", "0")
        )
    elif group_id is not None:
        group_ids = (group_id,)
    else:
        group_ids = ()
    credentials = Path(str(get("GOOGLE_CREDENTIALS_FILE", base / "credentials.json")))
    if not credentials.is_absolute():
        credentials = base / credentials
    return Stage4Config(
        telegram_bot_token=str(token),
        gemini_api_key=str(gemini),
        admin_user_id=int(admin),
        db_path=str(get("STAGE4_DB_PATH", base / "data" / "stage4_test.sqlite3")),
        gemini_model=str(get("GEMINI_MODEL", "gemini-3.1-flash-lite")),
        require_test_tag=_bool(get("STAGE4_REQUIRE_TEST_TAG", False), False),
        test_tag=str(get("STAGE4_TEST_TAG", "#تست")),
        enable_reaction_in_test=_bool(get("STAGE4_ENABLE_REACTION", True), True),
        group_chat_id=group_id,
        group_chat_ids=group_ids,
        sheets_enabled=_bool(get("STAGE4_SHEETS_ENABLED", True), True),
        spreadsheet_name=str(get("SPREADSHEET_NAME", "BARKAV1405")),
        google_credentials_file=str(credentials),
        sheets_sync_interval_seconds=max(5, int(get("STAGE4_SYNC_INTERVAL_SECONDS", 15))),
        sheets_sync_batch_size=max(1, int(get("STAGE4_SYNC_BATCH_SIZE", 25))),
        cheque_reminders_enabled=_bool(get("STAGE6_CHEQUE_REMINDERS_ENABLED", True), True),
        cheque_reminder_days_before=max(0, int(get("STAGE6_CHEQUE_REMINDER_DAYS_BEFORE", 5))),
        cheque_reminder_times=tuple(
            x.strip() for x in str(get("STAGE6_CHEQUE_REMINDER_TIMES", "09:00,14:00,19:00")).split(",") if x.strip()
        ),
        reminder_check_interval_seconds=max(30, int(get("STAGE6_REMINDER_CHECK_SECONDS", 60))),
        buyer_reminders_enabled=_bool(get("STAGE7_BUYER_REMINDERS_ENABLED", True), True),
        buyer_reminder_days_before=max(0, int(get("STAGE7_BUYER_REMINDER_DAYS_BEFORE", 3))),
        buyer_reminder_days_after=max(0, int(get("STAGE7_BUYER_REMINDER_DAYS_AFTER", 7))),
        buyer_reminder_time=str(get("STAGE7_BUYER_REMINDER_TIME", "09:00")),
    )
