"""WR-01: receipt inbox for the web upload channel.

Each uploaded photo is decoded, checked and re-encoded as JPEG. Re-encoding drops
EXIF metadata, including GPS coordinates. The photo and its caption are written to
separate files in a folder of their own.

Nothing in this module touches the financial tables. An item only waits in the
inbox until a person imports it into the approval queue.
"""

from __future__ import annotations

import io
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

CONTRACT_VERSION = 1  # RECEIPT_INBOX_V1 contract, see docs/contracts/RECEIPT_INBOX_V1.md
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_CAPTION_CHARS = 1000
MAX_EDGE_PX = 2400
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
STATE_RECEIVED = "RECEIVED"
STATE_IMPORTED = "IMPORTED"


class ReceiptRejected(ValueError):
    """The upload is not stored. The message is safe to show to the sender."""


@dataclass(frozen=True)
class StoredReceipt:
    receipt_id: str
    folder: Path


def new_pairing_token() -> str:
    return secrets.token_urlsafe(18)


def token_matches(expected: str, given: str) -> bool:
    if not expected or not given:
        return False
    return secrets.compare_digest(expected.encode("utf-8"), given.encode("utf-8"))


def _reencode(image_bytes: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(image_bytes)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(image_bytes)) as img:
            if img.format not in ALLOWED_FORMATS:
                raise ReceiptRejected("unsupported image type")
            rgb = img.convert("RGB")
    except ReceiptRejected:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as exc:
        raise ReceiptRejected("unreadable image") from exc

    rgb.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX))
    out = io.BytesIO()
    rgb.save(out, format="JPEG", quality=90)
    return out.getvalue()


def store_receipt(inbox_dir: Path, image_bytes: bytes, caption: str) -> StoredReceipt:
    if not image_bytes:
        raise ReceiptRejected("empty upload")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ReceiptRejected("image is too large")
    caption = (caption or "").strip()
    if len(caption) > MAX_CAPTION_CHARS:
        raise ReceiptRejected("caption is too long")

    jpeg = _reencode(image_bytes)

    now = datetime.now(timezone.utc)
    receipt_id = now.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4)
    folder = Path(inbox_dir) / receipt_id
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "receipt.jpg").write_bytes(jpeg)

    meta = {
        "schema_version": CONTRACT_VERSION,
        "receipt_id": receipt_id,
        "caption": caption,
        "received_at": now.isoformat(timespec="seconds"),
        "state": STATE_RECEIVED,
        "source": "web",
    }
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return StoredReceipt(receipt_id, folder)


def list_received(inbox_dir: Path) -> list[dict[str, Any]]:
    """Return the metadata of items that no one has imported yet, oldest first."""
    items: list[dict[str, Any]] = []
    root = Path(inbox_dir)
    if not root.is_dir():
        return items
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        meta_path = folder / "meta.json"
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("state") == STATE_RECEIVED:
            meta["folder"] = str(folder)
            items.append(meta)
    return items


def mark_imported(folder: Path, pending_id: str) -> None:
    """Record that the receipt reached the review queue. Keeps the photo and caption."""
    meta_path = Path(folder) / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["state"] = STATE_IMPORTED
    meta["pending_id"] = pending_id
    meta["imported_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
