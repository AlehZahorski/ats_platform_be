from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import UnprocessableError

_ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}
_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}


class FileStorageService:
    """Handles CV uploads to the local filesystem."""

    def __init__(self) -> None:
        self._upload_dir = Path(settings.cv_upload_dir)
        self._upload_dir.mkdir(parents=True, exist_ok=True)

    # F-H4 (audit_api): stream in 64 KiB chunks so a malicious uploader can't
    # exhaust RAM with a 10 GB body — we stop reading and raise as soon as we
    # cross ``max_upload_size_bytes``. The partial file is removed before we
    # surface the error so disk is not polluted either.
    _CHUNK_SIZE = 64 * 1024

    async def save_cv(self, file: UploadFile) -> str:
        """Validate and persist an uploaded CV file. Returns the stored file path."""
        self._validate(file)

        suffix = Path(file.filename or "").suffix.lower() or ".pdf"
        filename = f"{uuid.uuid4()}{suffix}"
        dest = self._upload_dir / filename
        max_bytes = settings.max_upload_size_bytes

        size = 0
        try:
            with dest.open("wb") as out:
                while True:
                    chunk = await file.read(self._CHUNK_SIZE)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        # Drop the partial file before raising to keep disk clean.
                        out.close()
                        dest.unlink(missing_ok=True)
                        raise UnprocessableError(
                            f"File exceeds maximum size of {settings.max_upload_size_mb} MB."
                        )
                    out.write(chunk)
        except UnprocessableError:
            raise
        except Exception:
            dest.unlink(missing_ok=True)
            raise

        return str(Path(settings.cv_upload_dir) / filename)

    def delete_cv(self, cv_url: str) -> None:
        """Remove a CV file from disk. Best-effort — ignores missing files."""
        path = Path(cv_url)
        if path.exists():
            path.unlink(missing_ok=True)

    def _validate(self, file: UploadFile) -> None:
        # F-M11 (audit_api): require BOTH MIME and extension to be on the
        # allowlist. The previous ``OR`` accepted ``Content-Type: application/pdf``
        # with a ``.exe`` extension (or vice-versa). Demanding both raises the
        # bar without breaking legitimate uploads from Word/Acrobat.
        content_type = (file.content_type or "").lower()
        extension = Path(file.filename or "").suffix.lower()
        if content_type not in _ALLOWED_TYPES or extension not in _ALLOWED_EXTENSIONS:
            raise UnprocessableError("Only PDF and DOCX files are accepted.")


file_storage = FileStorageService()
