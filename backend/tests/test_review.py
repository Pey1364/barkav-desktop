"""FD-12: the review queue (under review, approve or reject), tested on a temporary database."""

import base64

import pytest
from fastapi.testclient import TestClient

from barkav_field import envelope
from barkav_field.api import create_app
from barkav_field.intake import RemoteItem, pull_once
from barkav_field.store import ReviewError, Store

PASS = "test-passphrase-1"
REVIEW = {
    "title": "بابت آجر نما",
    "transaction_type": "پرداخت",
    "category": "مصالح",
    "document_kind": "financial",
    "note": "",
}


class MemInbox:
    """Keeps the order of insertion, like Drive lists files by creation time."""

    def __init__(self):
        self.blobs = {}

    def add(self, remote_id, payload):
        self.blobs[remote_id] = envelope.seal(payload, PASS)

    def list_items(self):
        return [RemoteItem(remote_id=key) for key in self.blobs]

    def download(self, remote_id):
        return self.blobs[remote_id]


def _receipt(receipt_id, review=None):
    payload = {
        "kind": "receipt",
        "id": receipt_id,
        "caption": "آجر",
        "received_at": "2026-10-16T10:00:00Z",
        "image_b64": base64.b64encode(b"\xff\xd8img").decode("ascii"),
    }
    if review is not None:
        payload["review"] = review
    return payload


def _decision(item_id, decision="approve"):
    return {"kind": "review_decision", "item_id": item_id, "decision": decision, "decided_at": "2026-10-16T11:00:00Z"}


# --- store rules --------------------------------------------------------------------

def test_receipt_without_classification_waits_as_new(tmp_path):
    store = Store(tmp_path)
    store.create_review_item(item_id="R-1")
    assert [row["id"] for row in store.list_review_items("new")] == ["R-1"]


def test_complete_classification_from_the_phone_puts_it_under_review(tmp_path):
    store = Store(tmp_path)
    store.create_review_item(item_id="R-1", classification=REVIEW)
    row = store.list_review_items("under_review")[0]
    assert row["title"] == "بابت آجر نما"
    assert row["document_kind"] == "financial"


def test_incomplete_classification_is_treated_as_missing(tmp_path):
    store = Store(tmp_path)
    store.create_review_item(item_id="R-1", classification={"title": "x", "transaction_type": "y"})
    assert [row["id"] for row in store.list_review_items("new")] == ["R-1"]


def test_creating_the_same_item_twice_changes_nothing(tmp_path):
    store = Store(tmp_path)
    assert store.create_review_item(item_id="R-1") is True
    assert store.create_review_item(item_id="R-1", classification=REVIEW) is False
    assert [row["id"] for row in store.list_review_items("new")] == ["R-1"]


def test_classify_moves_a_new_item_under_review(tmp_path):
    store = Store(tmp_path)
    store.create_review_item(item_id="R-1")
    store.classify("R-1", title="بابت آجر نما", transaction_type="پرداخت", document_kind="non_financial")
    assert store.list_review_items("under_review")[0]["document_kind"] == "non_financial"


def test_classify_refuses_a_missing_document_kind(tmp_path):
    store = Store(tmp_path)
    store.create_review_item(item_id="R-1")
    with pytest.raises(ReviewError):
        store.classify("R-1", title="x", transaction_type="y", document_kind="")


def test_document_kind_must_be_financial_or_non_financial(tmp_path):
    store = Store(tmp_path)
    store.create_review_item(item_id="R-1")
    with pytest.raises(ReviewError):
        store.classify("R-1", title="x", transaction_type="y", document_kind="cash")


def test_a_new_item_cannot_be_decided(tmp_path):
    store = Store(tmp_path)
    store.create_review_item(item_id="R-1")
    with pytest.raises(ReviewError):
        store.decide("R-1", decision="approve", decided_by="phone", decided_at="t")


def test_the_first_decision_wins(tmp_path):
    store = Store(tmp_path)
    store.create_review_item(item_id="R-1", classification=REVIEW)
    assert store.decide("R-1", decision="approve", decided_by="phone", decided_at="t1") is True
    assert store.decide("R-1", decision="reject", decided_by="desktop", decided_at="t2") is False
    row = store.list_review_items("approved")[0]
    assert row["decided_by"] == "phone"
    assert row["decided_at"] == "t1"


def test_a_decided_item_cannot_be_classified_again(tmp_path):
    store = Store(tmp_path)
    store.create_review_item(item_id="R-1", classification=REVIEW)
    store.decide("R-1", decision="approve", decided_by="desktop", decided_at="t1")
    with pytest.raises(ReviewError):
        store.classify("R-1", title="x", transaction_type="y", document_kind="financial")


def test_unknown_item_or_decider_is_refused(tmp_path):
    store = Store(tmp_path)
    store.create_review_item(item_id="R-1", classification=REVIEW)
    with pytest.raises(ReviewError):
        store.decide("missing", decision="approve", decided_by="phone", decided_at="t")
    with pytest.raises(ReviewError):
        store.decide("R-1", decision="approve", decided_by="robot", decided_at="t")


# --- pull -----------------------------------------------------------------------------

def test_phone_classification_and_phone_decision_are_applied_by_the_pull(tmp_path):
    inbox = MemInbox()
    inbox.add("drive-1", _receipt("R-1", review=REVIEW))
    store = Store(tmp_path)
    pull_once(inbox=inbox, store=store, passphrase=PASS)
    assert [row["id"] for row in store.list_review_items("under_review")] == ["R-1"]

    inbox.add("drive-2", _decision("R-1"))
    pull_once(inbox=inbox, store=store, passphrase=PASS)

    row = store.list_review_items("approved")[0]
    assert row["id"] == "R-1"
    assert row["decided_by"] == "phone"


def test_a_decision_that_arrives_first_is_retried_on_the_next_pull(tmp_path):
    store = Store(tmp_path)
    first_inbox = MemInbox()
    first_inbox.add("drive-2", _decision("R-1"))
    first = pull_once(inbox=first_inbox, store=store, passphrase=PASS)
    assert [remote_id for remote_id, _ in first.failed] == ["drive-2"]

    second_inbox = MemInbox()
    second_inbox.add("drive-1", _receipt("R-1", review=REVIEW))
    second_inbox.add("drive-2", _decision("R-1"))
    pull_once(inbox=second_inbox, store=store, passphrase=PASS)

    assert [row["id"] for row in store.list_review_items("approved")] == ["R-1"]


# --- API --------------------------------------------------------------------------------

def test_review_routes_list_classify_and_decide(tmp_path):
    Store(tmp_path).create_review_item(item_id="R-1")
    client = TestClient(create_app(tmp_path))
    assert [row["id"] for row in client.get("/api/v1/review-items?status=new").json()] == ["R-1"]

    body = {"title": "بابت آجر نما", "transaction_type": "پرداخت", "document_kind": "financial"}
    assert client.post("/api/v1/review-items/R-1/classify", json=body).status_code == 200
    assert client.post("/api/v1/review-items/R-1/decision", json={"decision": "approve"}).json() == {
        "ok": True,
        "changed": True,
    }
    assert client.post("/api/v1/review-items/R-1/decision", json={"decision": "reject"}).json()["changed"] is False


def test_review_route_refuses_an_unknown_item_with_a_conflict(tmp_path):
    client = TestClient(create_app(tmp_path))
    body = {"title": "x", "transaction_type": "y", "document_kind": "financial"}
    assert client.post("/api/v1/review-items/nope/classify", json=body).status_code == 409
