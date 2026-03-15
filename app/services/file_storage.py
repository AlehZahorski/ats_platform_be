from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

# Accepted MIME types
_ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}


class FileStorageService:
    """Handles CV uploads to local filesystem."""

    def __init__(self) -> None:
        self._upload_dir = Path(settings.cv_upload_dir)
        self._upload_dir.mkdir(parents=True, exist_ok=True)

    async def save_cv(self, file: UploadFile) -> str:
        """
        Validate and persist an uploaded CV file.

        Returns:
            Relative path to the stored file (stored in DB as cv_url).

        Raises:
            HTTPException 400: invalid file type or size.
        """
        self._validate(file)

        suffix = Path(file.filename or "").suffix.lower() or ".pdf"
        filename = f"{uuid.uuid4()}{suffix}"
        dest = self._upload_dir / filename

        contents = await file.read()
        if len(contents) > settings.max_upload_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds maximum size of {settings.max_upload_size_mb} MB",
            )

        dest.write_bytes(contents)
        return str(Path(settings.cv_upload_dir) / filename)

    def delete_cv(self, cv_url: str) -> None:
        """Remove a CV file from disk (best-effort, ignores missing files)."""
        path = Path(cv_url)
        if path.exists():
            path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _validate(self, file: UploadFile) -> None:
        content_type = file.content_type or ""
        filename = file.filename or ""
        extension = Path(filename).suffix.lower()

        if content_type not in _ALLOWED_TYPES and extension not in _ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF and DOCX files are accepted",
            )


file_storage = FileStorageService()
