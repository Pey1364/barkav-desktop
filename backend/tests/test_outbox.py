"""FD-12: the desktop's decisions reach the phone through the inbox (outbox and publish)."""

import base64

from fastapi.testclient import TestClient

from barkav_field import envelope
from barkav_field.api import create_app
from barkav_field.intake import RemoteItem, pull_once
from barkav_field.outbox import publish_pending
from barkav_field.store import Store

PASS = "test-passphrase-1"
REVIEW = {"title": "خرید زمین", "transaction_type": "چک", "document_kind": "financial", "event_date": "1405-07-24", "amount": "1"}


class RecordingOutbox:
    def __init__(self, fail=False):
        self.files = {}
        self.fail = fail

    def upload(self, name, content):
        if self.fail:
            raise OSError("network is down")
        self.files[name] = content
        return name


class MemInbox:
    def __init__(self):
        self.blobs = {}

    def add(self, remote_id, payload):
        self.blobs[remote_id] = envelope.seal(payload, PASS)

    def list_items(self):
        return [RemoteItem(remote_id=key) for key in self.blobs]

    def download(self, remote_id):
        return self.blobs[remote_id]


def _document_with_review(store, document_id="D-1"):
    store.add_document(document_id=document_id, mode="detailed", caption="x", received_at="t",
                       images=[b"\xff\xd8x"])
    store.create_review_item(item_id=document_id, classification=REVIEW)


def test_a_desktop_decision_is_queued_for_the_phone(tmp_path):
    store = Store(tmp_path)
    _document_with_review(store)
    store.decide("D-1", decision="approve", decided_by="desktop", decided_at="2026-10-16T09:00:00Z")

    queued = store.pending_outbox()

    assert [row["payload"] for row in queued] == [
        {"kind": "review_status", "item_id": "D-1", "status": "approved", "decided_at": "2026-10-16T09:00:00Z"}
    ]


def test_a_phone_decision_is_not_queued_back_to_the_phone(tmp_path):
    store = Store(tmp_path)
    _document_with_review(store)
    store.decide("D-1", decision="reject", decided_by="phone", decided_at="t")
    assert store.pending_outbox() == []


def test_publish_seals_the_status_and_marks_it_sent(tmp_path):
    store = Store(tmp_path)
    _document_with_review(store)
    store.decide("D-1", decision="reject", decided_by="desktop", decided_at="t")
    outbox = RecordingOutbox()

    report = publish_pending(store=store, outbox=outbox, passphrase=PASS)

    assert report.failed == 0 and len(report.sent) == 1
    (name, sealed), = outbox.files.items()
    assert name.startswith("D-1-")
    assert envelope.open_(sealed, PASS)["status"] == "rejected"
    assert store.pending_outbox() == []
    assert publish_pending(store=store, outbox=RecordingOutbox(), passphrase=PASS).sent == []


def test_a_failed_upload_stays_pending_for_the_next_pull(tmp_path):
    store = Store(tmp_path)
    _document_with_review(store)
    store.decide("D-1", decision="approve", decided_by="desktop", decided_at="t")

    report = publish_pending(store=store, outbox=RecordingOutbox(fail=True), passphrase=PASS)

    assert report.failed == 1
    assert len(store.pending_outbox()) == 1


def test_the_pull_ignores_its_own_published_status(tmp_path):
    store = Store(tmp_path)
    _document_with_review(store)
    inbox = MemInbox()
    inbox.add("drive-status", {"kind": "review_status", "item_id": "D-1", "status": "approved", "decided_at": "t"})

    report = pull_once(inbox=inbox, store=store, passphrase=PASS)

    assert report.failed == []
    assert report.duplicate == ["D-1"]


def test_a_decision_in_the_desktop_page_is_queued(tmp_path):
    store = Store(tmp_path)
    _document_with_review(store)
    client = TestClient(create_app(tmp_path))

    assert client.post("/api/v1/review-items/D-1/decision", json={"decision": "approve"}).json()["changed"] is True
    assert [row["payload"]["status"] for row in Store(tmp_path).pending_outbox()] == ["approved"]
