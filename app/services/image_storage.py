from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import UnprocessableError


_ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
}
_ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# Tighter limit than CVs — banners and logos shouldn't be heavy.
_MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB


class ImageStorageService:
    """Saves company-profile images (logo, banner, gallery) to local disk.

    Mirrors FileStorageService for CVs but lives in its own subdir so cleanup
    scripts and access policies can target images specifically. Returned URLs
    are relative (start with /uploads/…) — the FastAPI app already mounts the
    upload dir as static, so the FE can use the URL directly in <img src>.
    """

    def __init__(self, subdir: str) -> None:
        self._upload_dir = Path(settings.upload_dir) / subdir
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._subdir = subdir

    async def save(self, file: UploadFile) -> str:
        self._validate(file)

        suffix = Path(file.filename or "").suffix.lower() or ".png"
        if suffix == ".jpg":
            suffix = ".jpeg"
        filename = f"{uuid.uuid4()}{suffix}"
        dest = self._upload_dir / filename

        contents = await file.read()
        if len(contents) > _MAX_IMAGE_BYTES:
            raise UnprocessableError("Obraz nie może być większy niż 2 MB.")

        dest.write_bytes(contents)
        # Return the URL the FE will use — matches StaticFiles mount in main.py.
        return f"/uploads/{self._subdir}/{filename}"

    def delete(self, url: str | None) -> None:
        """Best-effort delete. Accepts the URL we previously returned (or any
        path starting with /uploads/) and removes it from disk. Missing files
        are not an error — we treat replacement as "make sure the old one is
        gone" rather than a strict invariant."""
        if not url or not url.startswith("/uploads/"):
            return
        # Strip the URL prefix to get a filesystem path under upload_dir.
        relative = url[len("/uploads/"):]
        path = Path(settings.upload_dir) / relative
        if path.exists():
            path.unlink(missing_ok=True)

    def _validate(self, file: UploadFile) -> None:
        content_type = (file.content_type or "").lower()
        extension = Path(file.filename or "").suffix.lower()
        if content_type not in _ALLOWED_IMAGE_TYPES and extension not in _ALLOWED_IMAGE_EXTENSIONS:
            raise UnprocessableError("Dozwolone formaty obrazów: PNG, JPG, WEBP.")


# Distinct subdirs so a cleanup query targeting logos doesn't sweep banners too.
company_logo_storage = ImageStorageService("company-logos")
company_banner_storage = ImageStorageService("company-banners")
company_gallery_storage = ImageStorageService("company-gallery")
