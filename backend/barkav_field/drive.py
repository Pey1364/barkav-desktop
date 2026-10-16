"""FD-06 (Drive part): Google Drive as the remote inbox.

Implements the RemoteInbox protocol from FD-05 with the Drive v3 REST API. Only files
visible under drive.file are used, which means files this app created or the user
picked. The inbox folder is created once and its id is stored locally.
"""

from __future__ import annotations

import json
import secrets
from typing import Callable

import httpx

from .intake import RemoteItem
from .oauth import OAuthError

DRIVE_API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
FOLDER_NAME = "BARKAV Field Inbox"
FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveError(RuntimeError):
    """A Drive request failed. The message never contains a token."""


def _check(response: httpx.Response) -> httpx.Response:
    if response.status_code != 200:
        raise DriveError(f"Drive request failed with HTTP {response.status_code}")
    return response


class DriveInbox:
    """RemoteInbox over Drive. `token` returns a current access token."""

    def __init__(self, *, http: httpx.Client, token: Callable[[], str], folder_id: str):
        self._http = http
        self._token = token
        self._folder_id = folder_id

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}"}

    def list_items(self):
        query = f"'{self._folder_id}' in parents and trashed = false"
        page_token = None
        while True:
            params = {
                "q": query,
                "fields": "nextPageToken,files(id,createdTime)",
                "orderBy": "createdTime",
                "pageSize": "200",
            }
            if page_token:
                params["pageToken"] = page_token
            response = _check(self._http.get(f"{DRIVE_API}/files", params=params, headers=self._headers(), timeout=30))
            data = response.json()
            for item in data.get("files", []):
                yield RemoteItem(remote_id=str(item["id"]))
            page_token = data.get("nextPageToken")
            if not page_token:
                return

    def download(self, remote_id: str) -> bytes:
        response = _check(
            self._http.get(
                f"{DRIVE_API}/files/{remote_id}",
                params={"alt": "media"},
                headers=self._headers(),
                timeout=60,
            )
        )
        return response.content


def upload_file(*, http: httpx.Client, token: Callable[[], str], folder_id: str, name: str, content: bytes) -> str:
    """Create a file in the folder with one multipart request and return its id."""
    boundary = f"barkav-{secrets.token_hex(12)}"
    metadata = json.dumps({"name": name, "parents": [folder_id]}).encode("utf-8")
    body = b"".join(
        [
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode("ascii"),
            metadata,
            f"\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n".encode("ascii"),
            content,
            f"\r\n--{boundary}--\r\n".encode("ascii"),
        ]
    )
    headers = {
        "Authorization": f"Bearer {token()}",
        "Content-Type": f"multipart/related; boundary={boundary}",
    }
    response = _check(
        http.post(
            f"{UPLOAD_API}/files",
            params={"uploadType": "multipart", "fields": "id"},
            content=body,
            headers=headers,
            timeout=120,
        )
    )
    file_id = response.json().get("id")
    if not file_id:
        raise DriveError("Drive did not return the uploaded file id")
    return str(file_id)


def trash_file(*, http: httpx.Client, token: Callable[[], str], file_id: str) -> None:
    """Move one file to Drive Trash (recoverable). Used only to clean up test entries."""
    _check(
        http.patch(
            f"{DRIVE_API}/files/{file_id}",
            params={"fields": "id"},
            json={"trashed": True},
            headers={"Authorization": f"Bearer {token()}"},
            timeout=30,
        )
    )


def find_or_create_folder(*, http: httpx.Client, token: Callable[[], str], name: str = FOLDER_NAME) -> str:
    """Return the id of the inbox folder, creating it in My Drive if it does not exist."""
    headers = {"Authorization": f"Bearer {token()}"}
    query = f"name = '{name}' and mimeType = '{FOLDER_MIME}' and trashed = false"
    found = _check(
        http.get(f"{DRIVE_API}/files", params={"q": query, "fields": "files(id)", "pageSize": "10"}, headers=headers, timeout=30)
    ).json()
    files = found.get("files", [])
    if files:
        return str(files[0]["id"])
    created = _check(
        http.post(
            f"{DRIVE_API}/files",
            params={"fields": "id"},
            json={"name": name, "mimeType": FOLDER_MIME},
            headers=headers,
            timeout=30,
        )
    ).json()
    folder_id = created.get("id")
    if not folder_id:
        raise OAuthError("Drive did not return the new folder id")
    return str(folder_id)
