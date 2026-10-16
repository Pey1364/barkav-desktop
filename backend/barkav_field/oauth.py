"""FD-06 (sign-in part): Google sign-in for the desktop with a local redirect.

One Web application client is used by both the desktop and the phone page, so both see
the same Drive files under drive.file. The desktop uses the authorization-code flow with
PKCE and a redirect to http://localhost:8765/callback. The refresh token is stored in a
local file that Git ignores. No secret or token is ever printed or logged.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/drive.file"
REDIRECT_HOST = "localhost"
REDIRECT_PORT = 8765
REDIRECT_PATH = "/callback"
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}"


class OAuthError(RuntimeError):
    """Sign-in failed. The message never contains a token or a secret."""


@dataclass(frozen=True)
class Settings:
    client_id: str
    client_secret: str


def load_settings(path: Path) -> Settings:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    client_id = str(data.get("google_web_client_id", ""))
    secret = str(data.get("google_web_client_secret", ""))
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise OAuthError("google_web_client_id is missing")
    if not secret or "PASTE" in secret:
        raise OAuthError("google_web_client_secret is missing or still a placeholder")
    return Settings(client_id=client_id, client_secret=secret)


def pkce_pair() -> tuple[str, str]:
    """Return (verifier, challenge) for PKCE with the S256 method."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_auth_url(settings: Settings, *, state: str, challenge: str) -> str:
    params = {
        "client_id": settings.client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def parse_callback(query: dict[str, list[str]], expected_state: str) -> str:
    """Return the authorization code, or raise OAuthError. Checks the state first."""
    if "error" in query:
        raise OAuthError("sign-in was cancelled or refused")
    state = query.get("state", [""])[0]
    if not state or not secrets.compare_digest(state, expected_state):
        raise OAuthError("state does not match; sign-in was not started by this app")
    code = query.get("code", [""])[0]
    if not code:
        raise OAuthError("no authorization code in the callback")
    return code


def _token_request(client: httpx.Client, form: dict[str, str]) -> dict:
    response = client.post(TOKEN_URL, data=form, timeout=30)
    if response.status_code != 200:
        raise OAuthError(f"token request failed with HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict) or "access_token" not in payload:
        raise OAuthError("token response has no access token")
    return payload


def exchange_code(client: httpx.Client, settings: Settings, *, code: str, verifier: str) -> dict:
    return _token_request(
        client,
        {
            "client_id": settings.client_id,
            "client_secret": settings.client_secret,
            "code": code,
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
    )


def refresh(client: httpx.Client, settings: Settings, refresh_token: str) -> dict:
    return _token_request(
        client,
        {
            "client_id": settings.client_id,
            "client_secret": settings.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )


class TokenSource:
    """Keeps a short-lived access token and refreshes it from the stored refresh token."""

    def __init__(self, *, client: httpx.Client, settings: Settings, refresh_token: str, clock=time.monotonic):
        self._client = client
        self._settings = settings
        self._refresh_token = refresh_token
        self._access = ""
        self._expires_at = 0.0
        self._clock = clock

    def access_token(self) -> str:
        if not self._access or self._clock() >= self._expires_at - 60:
            payload = refresh(self._client, self._settings, self._refresh_token)
            self._access = str(payload["access_token"])
            self._expires_at = self._clock() + float(payload.get("expires_in", 3600))
        return self._access


def save_refresh_token(path: Path, token_payload: dict) -> None:
    """Store only what is needed to refresh later. The file lives in a Git-ignored folder."""
    refresh_token = token_payload.get("refresh_token")
    if not refresh_token:
        raise OAuthError("Google did not return a refresh token; sign in again with consent")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"refresh_token": refresh_token}), encoding="utf-8")


def load_refresh_token(path: Path) -> str:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OAuthError("not signed in yet; run the sign-in command first") from exc
    token = str(data.get("refresh_token", ""))
    if not token:
        raise OAuthError("stored sign-in is empty; sign in again")
    return token


_DONE_PAGE = (
    "<!doctype html><meta charset='utf-8'><title>BARKAV Field</title>"
    "<body style='font-family:sans-serif;direction:rtl;padding:2em'>"
    "<h3>ورود انجام شد</h3><p>می‌توانی این پنجره را ببندی.</p></body>"
)


def run_loopback_signin(
    *,
    settings: Settings,
    token_path: Path,
    client: httpx.Client,
    open_browser=None,
    timeout: float = 300.0,
) -> None:
    """Open Google sign-in, wait for the one redirect, exchange the code, store the token."""
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    url = build_auth_url(settings, state=state, challenge=challenge)
    received: dict[str, list[str]] = {}
    done = threading.Event()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - base class name
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != REDIRECT_PATH:
                self.send_response(404)
                self.end_headers()
                return
            received.update(urllib.parse.parse_qs(parsed.query))
            body = _DONE_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            done.set()

        def log_message(self, format, *args):  # noqa: A002 - keep base signature; no logging
            return

    server = HTTPServer(("127.0.0.1", REDIRECT_PORT), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if open_browser is None:
            import webbrowser

            open_browser = webbrowser.open
        print("صفحه‌ی ورود گوگل باز می‌شود. اگر باز نشد، این نشانی را در مرورگر بگذار:")
        print(url)
        open_browser(url)
        if not done.wait(timeout):
            raise OAuthError("sign-in timed out; run the command again")
    finally:
        server.shutdown()
        server.server_close()

    code = parse_callback(received, state)
    payload = exchange_code(client, settings, code=code, verifier=verifier)
    save_refresh_token(token_path, payload)
    print("ورود ذخیره شد.")
