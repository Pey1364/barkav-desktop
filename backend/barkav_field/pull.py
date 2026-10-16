"""FD-09: command line for sign-in and for pulling new entries from Drive.

    python -m barkav_field.pull signin           one-time sign-in in the browser
    python -m barkav_field.pull set-passphrase   save the passphrase on this computer (typed here)
    python -m barkav_field.pull                  read new entries into the local database

The passphrase is taken from the environment variable named in local_config.json, then from
this computer's Credential Manager (FD-11), and only then typed in. It is never written to a file.
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
from .drive import DriveInbox, DriveOutbox, find_or_create_folder
from .intake import pull_once
from .outbox import publish_pending
from .passphrase import PassphraseError, load_passphrase, save_passphrase
from .store import Store

BACKEND_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BACKEND_DIR / "local_config.json"
DATA_DIR = BACKEND_DIR / "data"
TOKEN_PATH = DATA_DIR / "google_token.json"
FOLDER_PATH = DATA_DIR / "drive_folder.json"


def _passphrase(env_name: str) -> str:
    value = os.environ.get(env_name or "BARKAV_FIELD_PASSPHRASE", "")
    if value:
        return value
    return load_passphrase() or getpass.getpass("عبارت عبور ورودی‌ها: ")


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
    parser.add_argument("command", nargs="?", default="pull", choices=["pull", "signin", "set-passphrase"])
    args = parser.parse_args(argv)

    if args.command == "set-passphrase":
        first = getpass.getpass("عبارت عبور ورودی‌ها: ")
        second = getpass.getpass("تکرار عبارت عبور: ")
        if first != second:
            print("دو عبارت یکسان نیستند؛ چیزی ذخیره نشد.", file=sys.stderr)
            return 1
        try:
            save_passphrase(first)
        except PassphraseError as exc:
            print(f"خطا: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:  # the credential store error text is not printed
            print(f"ذخیره در مخزن رمز ویندوز انجام نشد ({type(exc).__name__}).", file=sys.stderr)
            return 1
        print("عبارت عبور روی این رایانه ذخیره شد.")
        return 0

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
            passphrase = _passphrase(env_name)
            report = pull_once(inbox=inbox, store=store, passphrase=passphrase)
            published = publish_pending(
                store=store,
                outbox=DriveOutbox(http=http, token=source.access_token, folder_id=folder_id),
                passphrase=passphrase,
            )
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
    print(f"تصمیم‌های منتشرشده برای گوشی: {len(published.sent)}")
    if published.failed:
        print(f"منتشر نشد (دوباره امتحان می‌شود): {published.failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
