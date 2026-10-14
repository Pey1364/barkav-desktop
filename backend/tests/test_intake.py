"""FD-05: pulling entries from a remote inbox. The inbox here is in memory."""

import base64

from barkav_field import envelope
from barkav_field.intake import RemoteItem, pull_once
from barkav_field.store import Store

PASS = "test-passphrase-1"
IMAGE = b"\xff\xd8test-image"


class MemoryInbox:
    def __init__(self, files):
        self.files = files
        self.downloads = 0

    def list_items(self):
        return [RemoteItem(remote_id=k) for k in self.files]

    def download(self, remote_id):
        self.downloads += 1
        return self.files[remote_id]


def _receipt(rid="R-1"):
    return envelope.seal(
        {
            "kind": "receipt",
            "id": rid,
            "caption": "بابت آجر",
            "received_at": "2026-10-14T10:00:00Z",
            "image_b64": base64.b64encode(IMAGE).decode("ascii"),
        },
        PASS,
    )


def _report(rid="D-1"):
    return envelope.seal({"kind": "daily_report", "id": rid, "report_date": "2026-10-14", "body": "گزارش"}, PASS)


def test_pull_stores_receipts_and_reports(tmp_path):
    store = Store(tmp_path)
    inbox = MemoryInbox({"f1": _receipt(), "f2": _report()})

    report = pull_once(inbox=inbox, store=store, passphrase=PASS)

    assert sorted(report.stored) == ["D-1", "R-1"]
    assert [r["id"] for r in store.list_receipts()] == ["R-1"]
    assert [r["id"] for r in store.list_daily_reports()] == ["D-1"]


def test_second_pull_reads_nothing_again(tmp_path):
    store = Store(tmp_path)
    inbox = MemoryInbox({"f1": _receipt()})
    pull_once(inbox=inbox, store=store, passphrase=PASS)
    downloads_after_first = inbox.downloads

    report = pull_once(inbox=inbox, store=store, passphrase=PASS)

    assert report.skipped_seen == ["f1"]
    assert report.stored == []
    assert inbox.downloads == downloads_after_first


def test_wrong_passphrase_is_reported_and_not_marked_seen(tmp_path):
    store = Store(tmp_path)
    inbox = MemoryInbox({"f1": _receipt()})

    report = pull_once(inbox=inbox, store=store, passphrase="wrong-passphrase")

    assert report.failed == [("f1", "EnvelopeError")]
    assert not store.is_seen("f1")
    retry = pull_once(inbox=inbox, store=store, passphrase=PASS)
    assert retry.stored == ["R-1"]


def test_same_receipt_in_two_files_is_stored_once(tmp_path):
    store = Store(tmp_path)
    inbox = MemoryInbox({"f1": _receipt("R-1"), "f2": _receipt("R-1")})

    report = pull_once(inbox=inbox, store=store, passphrase=PASS)

    assert report.stored == ["R-1"]
    assert report.duplicate == ["R-1"]
    assert len(store.list_receipts()) == 1


def test_unknown_kind_is_reported_and_does_not_block_others(tmp_path):
    store = Store(tmp_path)
    unknown = envelope.seal({"kind": "expense_v2", "id": "X"}, PASS)
    inbox = MemoryInbox({"f0": unknown, "f1": _report()})

    report = pull_once(inbox=inbox, store=store, passphrase=PASS)

    assert report.unknown_kind == ["f0"]
    assert report.stored == ["D-1"]
    assert store.is_seen("f0")


def test_broken_payload_is_reported_not_crashing(tmp_path):
    store = Store(tmp_path)
    bad = envelope.seal({"kind": "receipt", "id": "R-9"}, PASS)
    inbox = MemoryInbox({"f1": bad, "f2": _report()})

    report = pull_once(inbox=inbox, store=store, passphrase=PASS)

    assert report.failed and report.failed[0][0] == "f1"
    assert report.stored == ["D-1"]
