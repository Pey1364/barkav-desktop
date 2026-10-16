"""FD-06 and FD-09: Drive inbox and sign-in helpers, tested with a fake Drive (no network)."""

import base64
import hashlib
import json
import urllib.parse

import httpx
import pytest

from barkav_field import envelope, oauth
from barkav_field.drive import DriveError, DriveInbox, find_or_create_folder
from barkav_field.intake import pull_once
from barkav_field.store import Store

SETTINGS = oauth.Settings(client_id="1019915243-test.apps.googleusercontent.com", client_secret="test-secret-value")
PASS = "test-passphrase-1"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- OAuth helpers -------------------------------------------------------------------

def test_pkce_challenge_matches_verifier():
    verifier, challenge = oauth.pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    assert challenge == expected
    assert "=" not in verifier and "=" not in challenge


def test_auth_url_asks_for_drive_file_only_and_no_secret():
    url = oauth.build_auth_url(SETTINGS, state="abc", challenge="xyz")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert query["redirect_uri"] == [oauth.REDIRECT_URI]
    assert query["code_challenge_method"] == ["S256"]
    assert query["access_type"] == ["offline"]
    assert query["state"] == ["abc"]
    assert "client_secret" not in url
    assert "test-secret-value" not in url


def test_callback_with_wrong_state_is_refused():
    with pytest.raises(oauth.OAuthError):
        oauth.parse_callback({"state": ["other"], "code": ["c"]}, expected_state="expected")


def test_callback_with_error_is_refused():
    with pytest.raises(oauth.OAuthError):
        oauth.parse_callback({"error": ["access_denied"], "state": ["expected"]}, expected_state="expected")


def test_callback_with_matching_state_returns_code():
    assert oauth.parse_callback({"state": ["expected"], "code": ["the-code"]}, expected_state="expected") == "the-code"


def test_settings_reject_placeholder_secret(tmp_path):
    path = tmp_path / "local_config.json"
    path.write_text(json.dumps({"google_web_client_id": "1-x.apps.googleusercontent.com",
                                "google_web_client_secret": "PASTE-WEB-CLIENT-SECRET-HERE"}), encoding="utf-8")
    with pytest.raises(oauth.OAuthError):
        oauth.load_settings(path)


def test_settings_load_when_filled(tmp_path):
    path = tmp_path / "local_config.json"
    path.write_text(json.dumps({"google_web_client_id": "1-x.apps.googleusercontent.com",
                                "google_web_client_secret": "GOCSPX-test"}), encoding="utf-8")
    settings = oauth.load_settings(path)
    assert settings.client_id.endswith(".apps.googleusercontent.com")


def test_exchange_code_sends_verifier_and_returns_tokens():
    seen = {}

    def handler(request):
        seen["form"] = dict(urllib.parse.parse_qsl(request.content.decode()))
        return httpx.Response(200, json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600})

    payload = oauth.exchange_code(_client(handler), SETTINGS, code="c1", verifier="v1")
    assert payload["refresh_token"] == "rt"
    assert seen["form"]["code_verifier"] == "v1"
    assert seen["form"]["grant_type"] == "authorization_code"


def test_failed_token_request_does_not_leak_the_secret():
    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    with pytest.raises(oauth.OAuthError) as info:
        oauth.exchange_code(_client(handler), SETTINGS, code="c1", verifier="v1")
    assert "test-secret-value" not in str(info.value)
    assert "400" in str(info.value)


def test_token_source_refreshes_once_and_caches(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"access_token": f"at-{calls['n']}", "expires_in": 3600})

    now = {"t": 1000.0}
    source = oauth.TokenSource(client=_client(handler), settings=SETTINGS, refresh_token="rt", clock=lambda: now["t"])
    assert source.access_token() == "at-1"
    assert source.access_token() == "at-1"
    assert calls["n"] == 1
    now["t"] += 4000
    assert source.access_token() == "at-2"


def test_refresh_token_is_saved_and_loaded(tmp_path):
    path = tmp_path / "google_token.json"
    oauth.save_refresh_token(path, {"access_token": "at", "refresh_token": "rt-saved"})
    assert oauth.load_refresh_token(path) == "rt-saved"
    assert "at" not in path.read_text(encoding="utf-8")


def test_save_without_refresh_token_is_refused(tmp_path):
    with pytest.raises(oauth.OAuthError):
        oauth.save_refresh_token(tmp_path / "t.json", {"access_token": "at"})


def test_missing_sign_in_is_a_clear_error(tmp_path):
    with pytest.raises(oauth.OAuthError):
        oauth.load_refresh_token(tmp_path / "missing.json")


# --- Drive ---------------------------------------------------------------------------

class FakeDrive:
    """Just enough of Drive v3: folders, files in a folder, and media download."""

    def __init__(self, page_size=2):
        self.folders = {}
        self.files = {}
        self.page_size = page_size
        self.created_folders = 0

    def add_file(self, folder_id, file_id, content: bytes):
        self.files[file_id] = {"folder": folder_id, "content": content, "created": f"2026-10-16T10:00:{len(self.files):02d}Z"}

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization", "").startswith("Bearer ")
        path = request.url.path
        params = dict(request.url.params)
        if request.method == "GET" and path == "/drive/v3/files":
            q = params.get("q", "")
            if "mimeType" in q:
                matches = [{"id": fid} for fid, f in self.folders.items() if f["name"] in q]
                return httpx.Response(200, json={"files": matches})
            folder = q.split("'")[1]
            items = sorted(
                ((fid, f) for fid, f in self.files.items() if f["folder"] == folder),
                key=lambda pair: pair[1]["created"],
            )
            start = int(params.get("pageToken", "0"))
            chunk = items[start:start + self.page_size]
            body = {"files": [{"id": fid, "createdTime": f["created"]} for fid, f in chunk]}
            if start + self.page_size < len(items):
                body["nextPageToken"] = str(start + self.page_size)
            return httpx.Response(200, json=body)
        if request.method == "POST" and path == "/drive/v3/files":
            self.created_folders += 1
            new_id = f"folder-{self.created_folders}"
            name = json.loads(request.content)["name"]
            self.folders[new_id] = {"name": name}
            return httpx.Response(200, json={"id": new_id})
        if request.method == "GET" and path.startswith("/drive/v3/files/"):
            file_id = path.rsplit("/", 1)[1]
            return httpx.Response(200, content=self.files[file_id]["content"])
        return httpx.Response(404, json={"error": "not found"})


def _token():
    return "test-access-token"


def test_find_or_create_folder_creates_once_then_reuses():
    fake = FakeDrive()
    client = _client(fake.handler)
    first = find_or_create_folder(http=client, token=_token)
    fake.folders[first]["name"] = "BARKAV Field Inbox"
    second = find_or_create_folder(http=client, token=_token)
    assert first == second
    assert fake.created_folders == 1


def test_drive_inbox_lists_all_pages_and_downloads_bytes():
    fake = FakeDrive(page_size=2)
    for i in range(5):
        fake.add_file("F", f"file-{i}", f"bytes-{i}".encode())
    inbox = DriveInbox(http=_client(fake.handler), token=_token, folder_id="F")

    ids = [item.remote_id for item in inbox.list_items()]

    assert ids == [f"file-{i}" for i in range(5)]
    assert inbox.download("file-3") == b"bytes-3"


def test_drive_error_is_raised_for_failed_requests():
    def handler(request):
        return httpx.Response(403, json={"error": "forbidden"})

    inbox = DriveInbox(http=_client(handler), token=_token, folder_id="F")
    with pytest.raises(DriveError):
        list(inbox.list_items())


def test_end_to_end_pull_from_drive_into_the_local_store(tmp_path):
    fake = FakeDrive(page_size=1)
    receipt = envelope.seal(
        {"kind": "receipt", "id": "R-7", "caption": "بابت آجر", "received_at": "2026-10-16T10:00:00Z",
         "image_b64": base64.b64encode(b"\xff\xd8img").decode("ascii")},
        PASS,
    )
    report_bytes = envelope.seal({"kind": "daily_report", "id": "D-7", "report_date": "2026-10-16", "body": "گزارش"}, PASS)
    fake.add_file("F", "drive-1", receipt)
    fake.add_file("F", "drive-2", report_bytes)
    inbox = DriveInbox(http=_client(fake.handler), token=_token, folder_id="F")
    store = Store(tmp_path)

    report = pull_once(inbox=inbox, store=store, passphrase=PASS)
    again = pull_once(inbox=inbox, store=store, passphrase=PASS)

    assert sorted(report.stored) == ["D-7", "R-7"]
    assert again.stored == [] and sorted(again.skipped_seen) == ["drive-1", "drive-2"]
    assert [r["id"] for r in store.list_receipts()] == ["R-7"]
    assert [r["id"] for r in store.list_daily_reports()] == ["D-7"]


def test_drive_adapter_does_not_import_the_legacy_app():
    from pathlib import Path

    import ast

    source = Path(__file__).resolve().parents[1] / "barkav_field" / "drive.py"
    names = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    assert not any(n.startswith(("finance_db", "barkav", "tkinter", "telegram")) for n in names)
