"""Edit and delete of registered documents, from the phone and from the desktop."""

import base64

from fastapi.testclient import TestClient

from barkav_field import envelope
from barkav_field.api import create_app
from barkav_field.intake import RemoteItem, pull_once
from barkav_field.store import Store

PASS = "test-passphrase-1"
FULL_REVIEW = {
    "title": "هزینه ساخت",
    "transaction_type": "چک",
    "phase": "۰۳ - طراحی",
    "document_kind": "financial",
    "event_date": "1405-07-24",
    "amount": "1500000",
}


class MemInbox:
    def __init__(self):
        self.blobs = {}

    def add(self, remote_id, payload):
        self.blobs[remote_id] = envelope.seal(payload, PASS)

    def list_items(self):
        return [RemoteItem(remote_id=key) for key in self.blobs]

    def download(self, remote_id):
        return self.blobs[remote_id]


def _document(document_id, mode="quick", review=None):
    payload = {
        "kind": "document",
        "id": document_id,
        "mode": mode,
        "caption": "فاکتور اولیه",
        "received_at": "2026-10-16T10:00:00Z",
        "images_b64": [base64.b64encode(b"\xff\xd8photo").decode("ascii")],
    }
    if review is not None:
        payload["review"] = review
    return payload


def test_phase_is_stored_with_the_classification(tmp_path):
    store = Store(tmp_path)
    store.create_review_item(item_id="D-1", classification=FULL_REVIEW)
    assert store.get_review_item("D-1")["phase"] == "۰۳ - طراحی"


def test_delete_removes_the_document_its_photos_and_its_review(tmp_path):
    store = Store(tmp_path)
    store.add_document(document_id="D-1", mode="quick", caption="x", received_at="t", images=[b"\xff\xd8a"])
    store.create_review_item(item_id="D-1")

    assert store.delete_document("D-1", queue_for_phone=True) is True

    assert store.list_documents() == []
    assert store.get_review_item("D-1") is None
    assert not (tmp_path / "images" / "D-1-1.jpg").exists()
    assert [row["payload"] for row in store.pending_outbox()] == [{"kind": "document_delete", "id": "D-1"}]


def test_a_deleted_document_is_not_recreated_by_a_late_copy(tmp_path):
    store = Store(tmp_path)
    inbox = MemInbox()
    inbox.add("drive-1", _document("D-1"))
    inbox.add("drive-2", {"kind": "document_delete", "id": "D-1"})
    pull_once(inbox=inbox, store=store, passphrase=PASS)
    assert store.list_documents() == []

    # The original document arrives again later (for example, a slow copy): it stays deleted.
    late = MemInbox()
    late.add("drive-1", _document("D-1"))
    report = pull_once(inbox=late, store=store, passphrase=PASS)
    assert report.failed == []
    assert store.list_documents() == []


def test_a_phone_edit_changes_caption_and_classification(tmp_path):
    store = Store(tmp_path)
    inbox = MemInbox()
    inbox.add("drive-1", _document("D-1"))
    pull_once(inbox=inbox, store=store, passphrase=PASS)
    inbox.add("drive-2", {"kind": "document_edit", "id": "D-1", "caption": "فاکتور اصلاح‌شده", "review": FULL_REVIEW})

    pull_once(inbox=inbox, store=store, passphrase=PASS)

    assert store.list_documents()[0]["caption"] == "فاکتور اصلاح‌شده"
    row = store.list_review_items("under_review")[0]
    assert (row["id"], row["phase"], row["amount"]) == ("D-1", "۰۳ - طراحی", "1500000")


def test_an_edit_that_arrives_before_its_document_is_retried(tmp_path):
    store = Store(tmp_path)
    first = MemInbox()
    first.add("drive-2", {"kind": "document_edit", "id": "D-1", "caption": "نو", "review": None})
    assert [remote_id for remote_id, _ in pull_once(inbox=first, store=store, passphrase=PASS).failed] == ["drive-2"]

    second = MemInbox()
    second.add("drive-1", _document("D-1"))
    second.add("drive-2", {"kind": "document_edit", "id": "D-1", "caption": "نو", "review": None})
    pull_once(inbox=second, store=store, passphrase=PASS)

    assert store.list_documents()[0]["caption"] == "نو"


def test_a_decided_item_keeps_its_classification_when_edited_from_the_phone(tmp_path):
    store = Store(tmp_path)
    inbox = MemInbox()
    inbox.add("drive-1", _document("D-1", mode="detailed", review=FULL_REVIEW))
    pull_once(inbox=inbox, store=store, passphrase=PASS)
    store.decide("D-1", decision="approve", decided_by="desktop", decided_at="t")
    inbox.add("drive-2", {"kind": "document_edit", "id": "D-1", "caption": "شرح تازه", "review": {**FULL_REVIEW, "title": "ورودی"}})

    report = pull_once(inbox=inbox, store=store, passphrase=PASS)

    assert report.failed == []
    assert store.list_documents()[0]["caption"] == "شرح تازه"
    assert store.get_review_item("D-1")["title"] == "هزینه ساخت"


def test_desktop_edit_is_queued_for_the_phone(tmp_path):
    store = Store(tmp_path)
    store.add_document(document_id="D-1", mode="quick", caption="قدیمی", received_at="t", images=[b"\xff\xd8a"])
    store.create_review_item(item_id="D-1")

    store.edit_document("D-1", caption="جدید", review=FULL_REVIEW, queue_for_phone=True)

    queued = [row["payload"] for row in store.pending_outbox()]
    assert queued[-1]["kind"] == "document_edit"
    assert queued[-1]["caption"] == "جدید"
    assert queued[-1]["review"]["phase"] == "۰۳ - طراحی"


def test_api_edit_and_delete(tmp_path):
    store = Store(tmp_path)
    store.add_document(document_id="D-1", mode="quick", caption="قدیمی", received_at="t", images=[b"\xff\xd8a"])
    store.create_review_item(item_id="D-1")
    client = TestClient(create_app(tmp_path))

    edited = client.post("/api/v1/documents/D-1/edit", json={
        "caption": "شرح جدید",
        "title": "هزینه ساخت",
        "transaction_type": "نقدی",
        "phase": "۰۱ - خرید زمین",
        "document_kind": "financial",
        "event_date": "1405-07-24",
        "amount": "250000",
    })
    assert edited.status_code == 200
    assert client.get("/api/v1/documents").json()[0]["caption"] == "شرح جدید"

    deleted = client.delete("/api/v1/documents/D-1").json()
    assert deleted == {"ok": True, "existed": True}
    assert client.get("/api/v1/documents").json() == []
    kinds = [row["payload"]["kind"] for row in Store(tmp_path).pending_outbox()]
    assert kinds == ["document_edit", "document_delete"]
