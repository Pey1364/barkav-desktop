"""FD-12: publish the desktop's decisions to the inbox so the phone can show them.

The desktop never sends anything on its own. The pull command publishes what is waiting in
the outbox, sealed with the same passphrase, and marks each item sent only after the upload works.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from . import envelope
from .store import Store


class RemoteOutbox(Protocol):
    def upload(self, name: str, content: bytes) -> str: ...


@dataclass
class PublishReport:
    sent: list[int] = field(default_factory=list)
    failed: int = 0


def publish_pending(*, store: Store, outbox: RemoteOutbox, passphrase: str) -> PublishReport:
    report = PublishReport()
    for item in store.pending_outbox():
        try:
            sealed = envelope.seal(item["payload"], passphrase)
            outbox.upload(f"{item['payload']['item_id']}-{item['id']}.json", sealed)
        except Exception:
            # Keep it pending; the next pull tries again. The error text is not printed (it may hold data).
            report.failed += 1
            continue
        store.mark_outbox_sent(item["id"])
        report.sent.append(item["id"])
    return report
