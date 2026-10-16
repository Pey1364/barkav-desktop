"""FD-06 (Drive part): Google Drive as the remote inbox.

Implements the RemoteInbox protocol from FD-05 with the Drive v3 REST API. Only files
visible under drive.file are used, which means files this app created or the user
picked. The inbox folder is created once and its id is stored locally.
"""

from __future__ import annotations

from typing import Callable

import httpx

from .intake import RemoteItem
from .oauth import OAuthError

DRIVE_API = "https://www.googleapis.com/drive/v3"
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
