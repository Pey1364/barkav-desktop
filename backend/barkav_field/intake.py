"""FD-05: reads new field entries from a remote inbox and stores them.

The module depends only on the `RemoteInbox` protocol. A Google Drive adapter (FD-06)
implements that protocol later. Tests use an in-memory inbox.

For each remote item:
- an item already in `seen_remote` is skipped;
- a wrong passphrase or damaged envelope is reported and NOT marked seen, so it is
  tried again when the passphrase is corrected;
- an unknown `kind` is reported and marked seen, so it does not block the rest.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Iterable, Protocol

from . import envelope
from .store import Store


@dataclass(frozen=True)
class RemoteItem:
    remote_id: str


class RemoteInbox(Protocol):
    def list_items(self) -> Iterable[RemoteItem]: ...

    def download(self, remote_id: str) -> bytes: ...


@dataclass
class PullReport:
    stored: list[str] = field(default_factory=list)
    skipped_seen: list[str] = field(default_factory=list)
    duplicate: list[str] = field(default_factory=list)
    unknown_kind: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def _store_payload(store: Store, payload: dict) -> tuple[str, str] | None:
    """Store one decrypted payload. Returns (kind, entry_id), or None for unknown kinds."""
    kind = payload.get("kind")
    if kind == "receipt":
        image = base64.b64decode(str(payload["image_b64"]), validate=True)
        created = store.add_receipt(
            receipt_id=str(payload["id"]),
            caption=str(payload.get("caption", "")),
            received_at=str(payload["received_at"]),
            image_bytes=image,
        )
        return ("receipt", str(payload["id"])) if created else ("receipt-duplicate", str(payload["id"]))
    if kind == "daily_report":
        created = store.add_daily_report(
            report_id=str(payload["id"]),
            report_date=str(payload["report_date"]),
            body=str(payload["body"]),
        )
        return ("daily_report", str(payload["id"])) if created else ("daily_report-duplicate", str(payload["id"]))
    return None


def pull_once(*, inbox: RemoteInbox, store: Store, passphrase: str) -> PullReport:
    report = PullReport()
    for item in inbox.list_items():
        if store.is_seen(item.remote_id):
            report.skipped_seen.append(item.remote_id)
            continue
        try:
            payload = envelope.open_(inbox.download(item.remote_id), passphrase)
            outcome = _store_payload(store, payload)
        except (envelope.EnvelopeError, KeyError, ValueError, TypeError) as exc:
            report.failed.append((item.remote_id, type(exc).__name__))
            continue

        if outcome is None:
            report.unknown_kind.append(item.remote_id)
            store.mark_seen(remote_id=item.remote_id, kind="unknown", entry_id="")
            continue
        kind, entry_id = outcome
        store.mark_seen(remote_id=item.remote_id, kind=kind.split("-")[0], entry_id=entry_id)
        if kind.endswith("-duplicate"):
            report.duplicate.append(entry_id)
        else:
            report.stored.append(entry_id)
    return report
