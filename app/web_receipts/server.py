"""WR-02: local HTTP(S) server for the web receipt page.

The server runs inside the desktop application's process. It accepts photos only
from a sender who has the pairing token. Photos and captions go to the inbox
through `inbox.store_receipt`, which is the only place that writes them.

Routes:
    GET  /                    the receipt page
    GET  /sw.js               service worker (app shell only, no API caching)
    GET  /manifest.webmanifest
    GET  /icon-512.png
    POST /api/v1/receipts     body = image bytes; headers: Authorization: Bearer <token>,
                              X-Receipt-Caption: <percent-encoded UTF-8 caption>
"""

from __future__ import annotations

import json
import ssl
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from .inbox import MAX_IMAGE_BYTES, ReceiptRejected, store_receipt, token_matches

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_CAPTION_HEADER_BYTES = 4096

_STATIC_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/sw.js": ("sw.js", "application/javascript; charset=utf-8"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8"),
    "/icon-512.png": ("icon-512.png", "image/png"),
}


class ReceiptServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, *, inbox_dir: Path, token: str):
        super().__init__(address, handler)
        self.inbox_dir = Path(inbox_dir)
        self.token = token


class ReceiptHandler(BaseHTTPRequestHandler):
    server_version = "BARKAVReceipts"
    sys_version = ""

    def log_message(self, format, *args):  # noqa: A002 - keep the base signature
        # Requests may carry tokens or photos; nothing is written to the log.
        return

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, name: str, content_type: str) -> None:
        data = (STATIC_DIR / name).read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802 - base class name
        route = _STATIC_ROUTES.get(self.path.split("?", 1)[0])
        if route is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        self._send_static(*route)

    def do_POST(self):  # noqa: N802 - base class name
        if self.path.split("?", 1)[0] != "/api/v1/receipts":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        header = self.headers.get("Authorization", "")
        given = header[7:] if header.startswith("Bearer ") else ""
        if not token_matches(self.server.token, given):
            time.sleep(1)  # slows down guessing of the pairing code
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "pairing code is wrong"})
            return

        length_header = self.headers.get("Content-Length")
        if length_header is None:
            self._send_json(HTTPStatus.LENGTH_REQUIRED, {"error": "content length is required"})
            return
        try:
            length = int(length_header)
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "bad content length"})
            return
        if length <= 0:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "empty upload"})
            return
        if length > MAX_IMAGE_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "image is too large"})
            return

        raw_caption = self.headers.get("X-Receipt-Caption", "")
        if len(raw_caption.encode("utf-8", "replace")) > MAX_CAPTION_HEADER_BYTES:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "caption is too long"})
            return
        try:
            caption = unquote(raw_caption, encoding="utf-8", errors="strict") if raw_caption else ""
        except UnicodeDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "bad caption encoding"})
            return

        body = self.rfile.read(length)
        try:
            stored = store_receipt(self.server.inbox_dir, body, caption)
        except ReceiptRejected as exc:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
            return

        self._send_json(HTTPStatus.CREATED, {"receipt_id": stored.receipt_id})


def make_server(
    *,
    inbox_dir: Path,
    token: str,
    host: str = "0.0.0.0",
    port: int = 0,
    certfile: Path | None = None,
    keyfile: Path | None = None,
) -> ReceiptServer:
    """Bind the server. With a certificate it serves HTTPS, otherwise plain HTTP (tests only)."""
    server = ReceiptServer((host, port), ReceiptHandler, inbox_dir=inbox_dir, token=token)
    if certfile and keyfile:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(certfile), keyfile=str(keyfile))
        server.socket = context.wrap_socket(server.socket, server_side=True)
    return server
