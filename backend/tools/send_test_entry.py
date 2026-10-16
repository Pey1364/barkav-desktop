"""FD-10: developer check of the Google Drive round trip. Not part of the app.

    python -m tools.send_test_entry      (run from the backend folder)

It seals one test receipt with a random passphrase, uploads it to the inbox folder,
reads it back through the same Drive and decryption path as `pull` into a temporary
database, and then moves the uploaded file to Drive Trash (recoverable there).
The real local database and the real passphrase are never used.
"""

from __future__ import annotations

import base64
import secrets
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from barkav_field import envelope, oauth
from barkav_field.drive import DriveError, DriveInbox, find_or_create_folder, trash_file, upload_file
from barkav_field.intake import RemoteItem, pull_once
from barkav_field.pull import CONFIG_PATH, TOKEN_PATH
from barkav_field.store import Store

DUMMY_IMAGE = b"\xff\xd8test-image"


class _OnlyUploadedFile:
    """Shows only the uploaded file to pull_once, so real inbox entries are left alone."""

    def __init__(self, inbox: DriveInbox, file_id: str):
        self._inbox = inbox
        self._file_id = file_id

    def list_items(self):
        return [RemoteItem(remote_id=self._file_id)]

    def download(self, remote_id: str) -> bytes:
        return self._inbox.download(remote_id)


def main() -> int:
    # Windows consoles can use a legacy code page that cannot print Persian; use UTF-8.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    now = datetime.now(timezone.utc)
    entry_id = f"TEST-{now:%Y%m%d%H%M%S}"
    passphrase = secrets.token_urlsafe(24)  # random, used only in this run; never printed or saved
    http = httpx.Client()
    uploaded: str | None = None
    token = None
    try:
        settings = oauth.load_settings(CONFIG_PATH)
        source = oauth.TokenSource(client=http, settings=settings, refresh_token=oauth.load_refresh_token(TOKEN_PATH))
        token = source.access_token
        folder_id = find_or_create_folder(http=http, token=token)

        payload = {
            "kind": "receipt",
            "id": entry_id,
            "caption": "آزمایش اتصال Drive",
            "received_at": now.isoformat(timespec="seconds"),
            "image_b64": base64.b64encode(DUMMY_IMAGE).decode("ascii"),
        }
        uploaded = upload_file(
            http=http,
            token=token,
            folder_id=folder_id,
            name=f"{entry_id}.json",
            content=envelope.seal(payload, passphrase),
        )
        print("آپلود شد.")

        inbox = DriveInbox(http=http, token=token, folder_id=folder_id)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            report = pull_once(inbox=_OnlyUploadedFile(inbox, uploaded), store=store, passphrase=passphrase)
            receipt_ids = [row["id"] for row in store.list_receipts()]
    except (oauth.OAuthError, DriveError) as exc:
        print(f"خطا: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # keep the message short; no traceback with values
        print(f"خطا در تست Drive ({type(exc).__name__}).", file=sys.stderr)
        return 1
    finally:
        if uploaded and token is not None:
            try:
                trash_file(http=http, token=token, file_id=uploaded)
                print("فایل آزمایشی به سطل زباله‌ی Drive منتقل شد.")
            except Exception as exc:  # keep the id so it can be removed by hand
                print(f"فایل آزمایشی منتقل نشد ({type(exc).__name__}). شناسه: {uploaded}", file=sys.stderr)
        http.close()

    ok = report.stored == [entry_id] and receipt_ids == [entry_id]
    print(f"خوانده و رمزگشایی شد: {'بله' if entry_id in report.stored else 'نه'}")
    print(f"در دیتابیس موقت ذخیره شد: {'بله' if receipt_ids == [entry_id] else 'نه'}")
    if not ok:
        print(f"ناموفق (رمز یا داده): {report.failed}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
