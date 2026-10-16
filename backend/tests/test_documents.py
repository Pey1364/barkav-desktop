"""FD-13: documents with several photos, the two capture modes, and daily reports with details."""

import base64
import sqlite3

import pytest
from fastapi.testclient import TestClient

from barkav_field import envelope
from barkav_field.api import create_app
from barkav_field.intake import RemoteItem, pull_once
from barkav_field.store import Store

PASS = "test-passphrase-1"
REVIEW = {"title": "خرید زمین", "transaction_type": "پرداخت", "document_kind": "financial", "category": "", "note": ""}


class MemInbox:
    def __init__(self):
        self.blobs = {}

    def add(self, remote_id, payload):
        self.blobs[remote_id] = envelope.seal(payload, PASS)

    def list_items(self):
        return [RemoteItem(remote_id=key) for key in self.blobs]

    def download(self, remote_id):
        return self.blobs[remote_id]


def _photo(n):
    return base64.b64encode(b"\xff\xd8photo-" + str(n).encode("ascii")).decode("ascii")


def _document(document_id, mode, photos=2, review=None):
    payload = {
        "kind": "document",
        "id": document_id,
        "mode": mode,
        "caption": "فاکتور آجر نما",
        "received_at": "2026-10-16T10:00:00Z",
        "images_b64": [_photo(i) for i in range(1, photos + 1)],
    }
    if review is not None:
        payload["review"] = review
    return payload


# --- store ----------------------------------------------------------------------------

def test_document_keeps_all_its_photos_in_order(tmp_path):
    store = Store(tmp_path)
    store.add_document(document_id="D-1", mode="quick", caption="آجر", received_at="t", images=[b"a", b"b", b"c"])
    assert store.list_documents()[0]["image_count"] == 3
    assert (tmp_path / "images" / "D-1-3.jpg").read_bytes() == b"c"


def test_document_needs_at_least_one_photo(tmp_path):
    with pytest.raises(ValueError):
        Store(tmp_path).add_document(document_id="D-1", mode="quick", caption="", received_at="t", images=[])


def test_document_mode_must_be_quick_or_detailed(tmp_path):
    with pytest.raises(ValueError):
        Store(tmp_path).add_document(document_id="D-1", mode="fast", caption="", received_at="t", images=[b"a"])


def test_older_database_gets_the_details_column(tmp_path):
    con = sqlite3.connect(tmp_path / "field.sqlite3")
    con.execute("CREATE TABLE daily_reports (id TEXT PRIMARY KEY, report_date TEXT NOT NULL, body TEXT NOT NULL, imported_at TEXT NOT NULL)")
    con.execute("INSERT INTO daily_reports VALUES ('D-0', '2026-10-14', 'old', '2026-10-14T10:00:00+00:00')")
    con.commit()
    con.close()

    store = Store(tmp_path)
    assert store.list_daily_reports()[0]["details"] == {}
    assert store.add_daily_report(report_id="D-1", report_date="2026-10-16", body="new", details={"phase": "۰۱"})
    assert {row["id"]: row["details"] for row in store.list_daily_reports()} == {"D-0": {}, "D-1": {"phase": "۰۱"}}


# --- pull -------------------------------------------------------------------------------

def test_quick_document_waits_as_new_and_detailed_one_is_under_review(tmp_path):
    inbox = MemInbox()
    inbox.add("drive-1", _document("D-1", "quick"))
    inbox.add("drive-2", _document("D-2", "detailed", review=REVIEW))
    store = Store(tmp_path)

    report = pull_once(inbox=inbox, store=store, passphrase=PASS)

    assert sorted(report.stored) == ["D-1", "D-2"]
    assert [row["id"] for row in store.list_review_items("new")] == ["D-1"]
    assert [row["id"] for row in store.list_review_items("under_review")] == ["D-2"]
    assert sorted(row["mode"] for row in store.list_documents()) == ["detailed", "quick"]


def test_document_without_photos_fails_and_is_retried_later(tmp_path):
    inbox = MemInbox()
    inbox.add("drive-1", _document("D-1", "quick", photos=0))
    store = Store(tmp_path)
    report = pull_once(inbox=inbox, store=store, passphrase=PASS)
    assert [remote_id for remote_id, _ in report.failed] == ["drive-1"]
    assert store.list_documents() == []


def test_daily_report_details_are_read_by_the_pull(tmp_path):
    inbox = MemInbox()
    inbox.add("drive-1", {
        "kind": "daily_report",
        "id": "D-9",
        "report_date": "1405-07-25",
        "body": "نصب تیغه‌ها",
        "phase": "۱۳ - تیغه چینی",
        "weather": "آفتابی",
        "temperature": "",
    })
    store = Store(tmp_path)
    pull_once(inbox=inbox, store=store, passphrase=PASS)
    assert store.list_daily_reports()[0]["details"] == {"phase": "۱۳ - تیغه چینی", "weather": "آفتابی"}


# --- API --------------------------------------------------------------------------------

def test_documents_route_lists_photo_counts(tmp_path):
    Store(tmp_path).add_document(document_id="D-1", mode="quick", caption="آجر", received_at="t", images=[b"a", b"b"])
    client = TestClient(create_app(tmp_path))
    assert [(row["id"], row["image_count"]) for row in client.get("/api/v1/documents").json()] == [("D-1", 2)]


# --- phone classification of a quick document (FD-12, FD-13) ---------------------------

def _classification(item_id, **review):
    return {"kind": "review_classification", "item_id": item_id, "review": review}


def test_phone_classifies_a_quick_document_and_it_goes_under_review(tmp_path):
    inbox = MemInbox()
    inbox.add("drive-1", _document("D-1", "quick"))
    store = Store(tmp_path)
    pull_once(inbox=inbox, store=store, passphrase=PASS)
    assert [row["id"] for row in store.list_review_items("new")] == ["D-1"]

    inbox.add("drive-2", _classification("D-1", **REVIEW))
    pull_once(inbox=inbox, store=store, passphrase=PASS)

    assert [row["id"] for row in store.list_review_items("under_review")] == ["D-1"]


def test_classification_that_arrives_before_its_document_is_retried(tmp_path):
    store = Store(tmp_path)
    first = MemInbox()
    first.add("drive-2", _classification("D-1", **REVIEW))
    report = pull_once(inbox=first, store=store, passphrase=PASS)
    assert [remote_id for remote_id, _ in report.failed] == ["drive-2"]

    second = MemInbox()
    second.add("drive-1", _document("D-1", "quick"))
    second.add("drive-2", _classification("D-1", **REVIEW))
    pull_once(inbox=second, store=store, passphrase=PASS)

    assert [row["id"] for row in store.list_review_items("under_review")] == ["D-1"]


def test_a_late_classification_after_a_decision_is_ignored(tmp_path):
    inbox = MemInbox()
    inbox.add("drive-1", _document("D-1", "quick"))
    inbox.add("drive-2", _classification("D-1", **REVIEW))
    store = Store(tmp_path)
    pull_once(inbox=inbox, store=store, passphrase=PASS)
    store.decide("D-1", decision="approve", decided_by="desktop", decided_at="t")

    inbox.add("drive-3", _classification("D-1", **{**REVIEW, "title": "ورودی"}))
    report = pull_once(inbox=inbox, store=store, passphrase=PASS)

    assert report.failed == []
    assert store.list_review_items("approved")[0]["title"] == "خرید زمین"


def test_daily_report_calendar_is_kept_in_details(tmp_path):
    inbox = MemInbox()
    inbox.add("drive-1", {"kind": "daily_report", "id": "D-10", "report_date": "1405-07-24",
                          "body": "بتن ریزی", "calendar": "jalali"})
    store = Store(tmp_path)
    pull_once(inbox=inbox, store=store, passphrase=PASS)
    assert store.list_daily_reports()[0]["details"] == {"calendar": "jalali"}


def test_classification_keeps_the_event_date_and_amount(tmp_path):
    store = Store(tmp_path)
    store.create_review_item(item_id="D-1")
    store.classify("D-1", title="خرید زمین", transaction_type="چک", document_kind="financial",
                   event_date="1405-07-24", amount="250000000")
    row = store.list_review_items("under_review")[0]
    assert (row["event_date"], row["amount"]) == ("1405-07-24", "250000000")


# --- desktop page support (FD-07 desktop part) -------------------------------------------

def test_document_photo_is_served_as_jpeg(tmp_path):
    store = Store(tmp_path)
    store.add_document(document_id="D-1", mode="quick", caption="", received_at="t", images=[b"\xff\xd8one", b"\xff\xd8two"])
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/v1/documents/D-1/images/2")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b"\xff\xd8two"


def test_missing_photo_is_not_found(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/v1/documents/none/images/1").status_code == 404


def test_desktop_server_allows_only_the_desktop_page_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("BARKAV_FIELD_DATA_DIR", str(tmp_path))
    from barkav_field import server

    client = TestClient(server.app)
    allowed = client.get("/api/v1/health", headers={"Origin": "http://127.0.0.1:5173"})
    refused = client.get("/api/v1/health", headers={"Origin": "https://example.com"})
    assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
    assert "access-control-allow-origin" not in refused.headers
