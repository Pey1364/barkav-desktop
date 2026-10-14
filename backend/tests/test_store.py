"""FD-02: local store. Every test uses its own temporary folder."""

import hashlib

from barkav_field.store import Store


def test_receipt_is_stored_once(tmp_path):
    store = Store(tmp_path)
    image = b"\xff\xd8fake-jpeg"
    assert store.add_receipt(receipt_id="R-1", caption="آجر", received_at="2026-10-14T10:00:00Z", image_bytes=image)
    assert not store.add_receipt(receipt_id="R-1", caption="again", received_at="2026-10-14T10:00:00Z", image_bytes=image)
    rows = store.list_receipts()
    assert [r["id"] for r in rows] == ["R-1"]
    assert rows[0]["caption"] == "آجر"
    assert rows[0]["image_sha256"] == hashlib.sha256(image).hexdigest()
    assert (tmp_path / "images" / "R-1.jpg").read_bytes() == image


def test_list_receipts_does_not_return_image_bytes(tmp_path):
    store = Store(tmp_path)
    store.add_receipt(receipt_id="R-1", caption="", received_at="2026-10-14T10:00:00Z", image_bytes=b"x")
    assert "image_bytes" not in store.list_receipts()[0]


def test_daily_reports_are_listed_newest_date_first(tmp_path):
    store = Store(tmp_path)
    store.add_daily_report(report_id="D-1", report_date="2026-10-13", body="دیروز")
    store.add_daily_report(report_id="D-2", report_date="2026-10-14", body="امروز")
    assert [r["id"] for r in store.list_daily_reports()] == ["D-2", "D-1"]


def test_seen_remote_is_recorded(tmp_path):
    store = Store(tmp_path)
    assert not store.is_seen("file-1")
    store.mark_seen(remote_id="file-1", kind="receipt", entry_id="R-1")
    assert store.is_seen("file-1")
    store.mark_seen(remote_id="file-1", kind="receipt", entry_id="R-1")
