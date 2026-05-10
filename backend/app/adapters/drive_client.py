"""Google Drive adapter — google-api-python-client wrapped via asyncio.to_thread.

Per ARCH-001 §4.3 / D5 — `drive.readonly` scope only. We never write to Drive.

The official google-api-python-client is synchronous. Rather than introduce a
second async-Drive SDK (e.g., `aiogoogle`) we offload calls to a worker thread.
At Phase-4 scale (a few list calls per scan, infrequent file downloads) this is
the right trade — adding a dep is more risk than the latency hit of `to_thread`.

Lessons-learned applied:
- framework-gotcha.md "Lazy Imports Hide Missing Dependencies" — `google.oauth2`
  and `googleapiclient` are imported at module top so missing deps surface at
  app boot, not at first /drive call.
- api-design.md "HTTP Retry Must Handle Both Transport and Application Errors" —
  rate-limit (429) and server-error (5xx) classification handled here so callers
  see typed exceptions.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Final

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.exceptions import (
    DriveError,
    DriveFileNotFoundError,
    DriveQuotaExceededError,
)

logger = logging.getLogger(__name__)

# Drive folder MIME type — used for `mimeType=...` filters
FOLDER_MIME: Final[str] = "application/vnd.google-apps.folder"


@dataclass(frozen=True)
class DriveItem:
    drive_file_id: str
    name: str
    mime_type: str
    is_folder: bool
    size_bytes: int | None
    modified_time: str  # ISO8601 string from Drive

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> DriveItem:
        mt = payload.get("mimeType", "")
        return cls(
            drive_file_id=payload["id"],
            name=payload["name"],
            mime_type=mt,
            is_folder=mt == FOLDER_MIME,
            size_bytes=int(payload["size"]) if payload.get("size") else None,
            modified_time=payload.get("modifiedTime", ""),
        )


class DriveClient:
    """Async-friendly wrapper over googleapiclient.discovery's drive.v3 service.

    Build a fresh service per teacher (the credentials object differs); cache it
    for the lifetime of the request. For longer-running operations (batch worker)
    callers should construct one DriveClient and reuse it across calls.
    """

    def __init__(self, credentials: Credentials) -> None:
        # `cache_discovery=False` avoids a noisy warning when google-auth-httplib2
        # isn't installed for the deprecated discovery cache. Build is sync.
        self._service = build(
            "drive", "v3", credentials=credentials, cache_discovery=False
        )

    async def list_folders_in(
        self, parent_id: str, *, page_size: int = 100
    ) -> list[DriveItem]:
        """List immediate subfolders of `parent_id` (one level deep)."""

        def _sync() -> list[DriveItem]:
            try:
                resp = (
                    self._service.files()
                    .list(
                        q=f"'{parent_id}' in parents and mimeType='{FOLDER_MIME}' and trashed=false",
                        fields="files(id,name,mimeType,modifiedTime)",
                        pageSize=page_size,
                        spaces="drive",
                    )
                    .execute()
                )
                return [DriveItem.from_api(f) for f in resp.get("files", [])]
            except HttpError as exc:
                raise _classify_http_error(exc) from exc

        return await asyncio.to_thread(_sync)

    async def list_files_in(
        self, parent_id: str, *, page_size: int = 200
    ) -> list[DriveItem]:
        """List immediate non-folder children of `parent_id`."""

        def _sync() -> list[DriveItem]:
            try:
                items: list[DriveItem] = []
                page_token: str | None = None
                while True:
                    resp = (
                        self._service.files()
                        .list(
                            q=(
                                f"'{parent_id}' in parents and "
                                f"mimeType != '{FOLDER_MIME}' and trashed=false"
                            ),
                            fields=(
                                "nextPageToken, "
                                "files(id,name,mimeType,size,modifiedTime)"
                            ),
                            pageSize=page_size,
                            pageToken=page_token,
                            spaces="drive",
                        )
                        .execute()
                    )
                    items.extend(DriveItem.from_api(f) for f in resp.get("files", []))
                    page_token = resp.get("nextPageToken")
                    if not page_token:
                        break
                return items
            except HttpError as exc:
                raise _classify_http_error(exc) from exc

        return await asyncio.to_thread(_sync)

    async def download_file(self, *, drive_file_id: str) -> bytes:
        """Download file content as bytes.

        Streams to an in-memory buffer via MediaIoBaseDownload. Suitable for V1
        scale (single .docx ~MB). Audio (>100MB) gets a separate streaming
        method in Phase 5+.
        """
        from googleapiclient.http import MediaIoBaseDownload  # local: heavy import
        import io as _io

        def _sync() -> bytes:
            try:
                request = self._service.files().get_media(fileId=drive_file_id)
                buf = _io.BytesIO()
                downloader = MediaIoBaseDownload(buf, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                return buf.getvalue()
            except HttpError as exc:
                raise _classify_http_error(exc) from exc

        return await asyncio.to_thread(_sync)

    async def list_root_folders(self, *, page_size: int = 100) -> list[DriveItem]:
        """List top-level folders in My Drive — for the onboarding 'pick root' UI."""

        def _sync() -> list[DriveItem]:
            try:
                resp = (
                    self._service.files()
                    .list(
                        q=(
                            f"'root' in parents and mimeType='{FOLDER_MIME}' "
                            "and trashed=false"
                        ),
                        fields="files(id,name,mimeType,modifiedTime)",
                        pageSize=page_size,
                        spaces="drive",
                    )
                    .execute()
                )
                return [DriveItem.from_api(f) for f in resp.get("files", [])]
            except HttpError as exc:
                raise _classify_http_error(exc) from exc

        return await asyncio.to_thread(_sync)


def _classify_http_error(exc: HttpError) -> DriveError:
    """Map googleapiclient's HttpError to typed DriveErrors.

    Per framework-gotcha.md "HTTP Client SDK Error Structure Varies": HttpError
    exposes `.resp.status` (int) reliably; we don't need a regex fallback here
    since this is a single-vendor SDK with a stable shape.
    """
    status = exc.resp.status if exc.resp else None
    if status == 404:
        return DriveFileNotFoundError(
            "Drive file not found or permission revoked",
            context={"status": 404, "raw": str(exc)},
        )
    if status == 429:
        return DriveQuotaExceededError(
            "Drive API quota / rate limit",
            context={"status": 429, "raw": str(exc)},
        )
    return DriveError(
        f"Drive API error (status={status})",
        context={"status": status, "raw": str(exc)},
    )
