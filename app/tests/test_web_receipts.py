"""Web receipt channel: storage rules, pairing, and the HTTP round trip.

Every test writes only into its own temporary folder. Photos here are generated in
memory, not real receipts.
"""

from __future__ import annotations

import io
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest
from PIL import Image

from web_receipts import inbox
from web_receipts.cert import ensure_certificate
from web_receipts.inbox import ReceiptRejected, list_received, new_pairing_token, store_receipt, token_matches
from web_receipts.server import make_server


def _jpeg_with_gps(size=(320, 240)) -> bytes:
    img = Image.new("RGB", size, (250, 250, 250))
    exif = Image.Exif()
    exif[0x0110] = "TestCamera"  # Model
    gps = exif.get_ifd(0x8825)  # GPS IFD
    gps[1] = "N"
    gps[2] = (35.0, 41.0, 0.0)
    exif[0x8825] = gps
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif.tobytes())
    return out.getvalue()


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 40), (10, 20, 30)).save(out, format="PNG")
    return out.getvalue()


def test_stored_photo_has_no_exif_or_gps_and_is_jpeg(tmp_path: Path):
    source = _jpeg_with_gps()
    assert Image.open(io.BytesIO(source)).getexif(), "fixture must carry EXIF to prove it is removed"

    stored = store_receipt(tmp_path, source, "")

    saved = stored.folder / "receipt.jpg"
    with Image.open(saved) as img:
        assert img.format == "JPEG"
        assert not img.getexif()
        assert "exif" not in img.info
    assert saved.read_bytes()[:2] == b"\xff\xd8"


def test_caption_is_kept_in_metadata_not_in_the_image(tmp_path: Path):
    stored = store_receipt(tmp_path, _png(), "  بابت خرید آجر  ")

    meta = json.loads((stored.folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["caption"] == "بابت خرید آجر"
    assert meta["state"] == "RECEIVED"
    assert meta["source"] == "web"
    assert (stored.folder / "receipt.jpg").is_file()


def test_png_is_accepted_and_converted(tmp_path: Path):
    stored = store_receipt(tmp_path, _png(), "")
    with Image.open(stored.folder / "receipt.jpg") as img:
        assert img.format == "JPEG"


def test_empty_upload_is_rejected(tmp_path: Path):
    with pytest.raises(ReceiptRejected):
        store_receipt(tmp_path, b"", "")


def test_non_image_bytes_are_rejected_and_nothing_is_written(tmp_path: Path):
    with pytest.raises(ReceiptRejected):
        store_receipt(tmp_path, b"not an image at all", "")
    assert not any(tmp_path.iterdir())


def test_unsupported_image_type_is_rejected(tmp_path: Path):
    out = io.BytesIO()
    Image.new("P", (20, 20)).save(out, format="GIF")
    with pytest.raises(ReceiptRejected):
        store_receipt(tmp_path, out.getvalue(), "")


def test_oversized_upload_is_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(inbox, "MAX_IMAGE_BYTES", 100)
    with pytest.raises(ReceiptRejected):
        store_receipt(tmp_path, _png(), "")


def test_overlong_caption_is_rejected(tmp_path: Path):
    with pytest.raises(ReceiptRejected):
        store_receipt(tmp_path, _png(), "x" * (inbox.MAX_CAPTION_CHARS + 1))


def test_list_received_returns_only_items_nobody_imported(tmp_path: Path):
    first = store_receipt(tmp_path, _png(), "one")
    second = store_receipt(tmp_path, _png(), "two")
    meta_path = second.folder / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["state"] = "IMPORTED"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    received = list_received(tmp_path)

    assert [item["receipt_id"] for item in received] == [first.receipt_id]


def test_token_check_rejects_missing_and_wrong_codes():
    token = new_pairing_token()
    assert token_matches(token, token)
    assert not token_matches(token, "")
    assert not token_matches(token, token + "x")
    assert not token_matches("", "")


def test_pairing_codes_are_unpredictable_enough():
    tokens = {new_pairing_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 20 for t in tokens)


def test_certificate_is_created_once_and_reused(tmp_path: Path):
    cert1, key1 = ensure_certificate(tmp_path, ["127.0.0.1", "receipts.local"])
    before = cert1.read_bytes()
    cert2, key2 = ensure_certificate(tmp_path, ["127.0.0.1"])
    assert cert2.read_bytes() == before
    assert key1.read_bytes().startswith(b"-----BEGIN")


@pytest.fixture()
def running_server(tmp_path: Path):
    token = "test-pairing-code-123456"
    server = make_server(inbox_dir=tmp_path / "inbox", token=token, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield base, token, tmp_path / "inbox"
    finally:
        server.shutdown()
        server.server_close()


def _post(base: str, body: bytes, headers: dict[str, str]):
    request = urllib.request.Request(f"{base}/api/receipts", data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


def test_page_is_served_as_right_to_left_persian(running_server):
    base, _, _ = running_server
    with urllib.request.urlopen(f"{base}/", timeout=10) as response:
        html = response.read().decode("utf-8")
    assert 'dir="rtl"' in html
    assert 'lang="fa"' in html


def test_upload_without_the_pairing_code_is_refused_and_stores_nothing(running_server):
    base, _, inbox_dir = running_server
    status, payload = _post(base, _png(), {"Content-Type": "image/png"})
    assert status == 401
    assert "receipt_id" not in payload
    assert not inbox_dir.exists() or not any(inbox_dir.iterdir())


def test_upload_with_the_wrong_code_is_refused(running_server):
    base, _, _ = running_server
    status, _ = _post(
        base, _png(), {"Content-Type": "image/png", "Authorization": "Bearer wrong-code"}
    )
    assert status == 401


def test_valid_upload_is_stored_with_a_persian_caption(running_server):
    base, token, inbox_dir = running_server
    caption = "بابت خرید آجر و ملات"
    status, payload = _post(
        base,
        _jpeg_with_gps(),
        {
            "Content-Type": "image/jpeg",
            "Authorization": f"Bearer {token}",
            "X-Receipt-Caption": urllib.parse.quote(caption, safe=""),
        },
    )
    assert status == 201
    folder = inbox_dir / payload["receipt_id"]
    assert (folder / "receipt.jpg").is_file()
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["caption"] == caption


def test_non_image_upload_with_the_right_code_is_refused(running_server):
    base, token, _ = running_server
    status, payload = _post(
        base, b"<script>alert(1)</script>", {"Content-Type": "image/png", "Authorization": f"Bearer {token}"}
    )
    assert status == 422
    assert "receipt_id" not in payload


def test_bad_caption_encoding_is_refused(running_server):
    base, token, _ = running_server
    status, _ = _post(
        base,
        _png(),
        {"Content-Type": "image/png", "Authorization": f"Bearer {token}", "X-Receipt-Caption": "%FF%FE"},
    )
    assert status == 400


def test_unknown_routes_are_not_found(running_server):
    base, _, _ = running_server
    with pytest.raises(urllib.error.HTTPError) as info:
        urllib.request.urlopen(f"{base}/admin", timeout=10)
    assert info.value.code == 404
