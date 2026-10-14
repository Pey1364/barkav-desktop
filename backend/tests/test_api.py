"""FD-03 and FD-04: local read API."""

from fastapi.testclient import TestClient

from barkav_field.api import create_app
from barkav_field.store import Store


def test_health(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/v1/health").json() == {"ok": True, "api": 1}


def test_receipts_and_reports_are_listed(tmp_path):
    store = Store(tmp_path)
    store.add_receipt(receipt_id="R-1", caption="آجر", received_at="2026-10-14T10:00:00Z", image_bytes=b"x")
    store.add_daily_report(report_id="D-1", report_date="2026-10-14", body="گزارش")
    client = TestClient(create_app(tmp_path))

    receipts = client.get("/api/v1/receipts").json()
    reports = client.get("/api/v1/daily-reports").json()

    assert [r["id"] for r in receipts] == ["R-1"]
    assert [r["id"] for r in reports] == ["D-1"]


def test_there_is_no_write_route(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.post("/api/v1/receipts", json={}).status_code == 405
    assert client.post("/api/v1/daily-reports", json={}).status_code == 405
