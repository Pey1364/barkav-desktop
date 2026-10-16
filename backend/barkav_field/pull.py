"""FD-09: command line for sign-in and for pulling new entries from Drive.

    python -m barkav_field.pull signin     one-time sign-in in the browser
    python -m barkav_field.pull           read new entries into the local database

The passphrase is read from the environment variable named in local_config.json, or
typed in when the variable is empty. It is never written to disk.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

import httpx

from . import oauth
from .drive import DriveInbox, find_or_create_folder
from .intake import pull_once
from .store import Store

BACKEND_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BACKEND_DIR / "local_config.json"
DATA_DIR = BACKEND_DIR / "data"
TOKEN_PATH = DATA_DIR / "google_token.json"
FOLDER_PATH = DATA_DIR / "drive_folder.json"


def _passphrase(env_name: str) -> str:
    value = os.environ.get(env_name or "BARKAV_FIELD_PASSPHRASE", "")
    return value or getpass.getpass("عبارت عبور ورودی‌ها: ")


def _folder_id(http: httpx.Client, token) -> str:
    if FOLDER_PATH.is_file():
        return str(json.loads(FOLDER_PATH.read_text(encoding="utf-8"))["folder_id"])
    folder_id = find_or_create_folder(http=http, token=token)
    FOLDER_PATH.write_text(json.dumps({"folder_id": folder_id}), encoding="utf-8")
    return folder_id


def main(argv: list[str] | None = None) -> int:
    # Windows consoles can use a legacy code page that cannot print Persian; use UTF-8.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="BARKAV Field: sign in and pull entries.")
    parser.add_argument("command", nargs="?", default="pull", choices=["pull", "signin"])
    args = parser.parse_args(argv)

    try:
        settings = oauth.load_settings(CONFIG_PATH)
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        env_name = str(raw.get("passphrase_env", "BARKAV_FIELD_PASSPHRASE"))

        with httpx.Client() as http:
            if args.command == "signin":
                oauth.run_loopback_signin(settings=settings, token_path=TOKEN_PATH, client=http)
                return 0

            source = oauth.TokenSource(
                client=http,
                settings=settings,
                refresh_token=oauth.load_refresh_token(TOKEN_PATH),
            )
            folder_id = _folder_id(http, source.access_token)
            inbox = DriveInbox(http=http, token=source.access_token, folder_id=folder_id)
            store = Store(DATA_DIR)
            report = pull_once(inbox=inbox, store=store, passphrase=_passphrase(env_name))
    except (oauth.OAuthError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"خطا: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # keep the message short; no traceback with values
        print(f"خطا در خواندن از Drive ({type(exc).__name__}).", file=sys.stderr)
        return 1

    print(f"ذخیره شد: {len(report.stored)}")
    print(f"قبلاً خوانده شده: {len(report.skipped_seen)}")
    print(f"تکراری: {len(report.duplicate)}")
    print(f"نوع ناشناخته: {len(report.unknown_kind)}")
    print(f"ناموفق (رمز یا داده): {len(report.failed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
