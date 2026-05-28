from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.core.exceptions import NotFoundError, UnprocessableError
from app.modules.companies.repository import CompanyRepository
from app.modules.companies.schemas import (
    CompanyRead,
    CompanyUpdate,
    GalleryItem,
)
from app.modules.companies.service import CompanyService
from app.services.image_storage import (
    company_banner_storage,
    company_gallery_storage,
    company_logo_storage,
)

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> CompanyService:
    return CompanyService(CompanyRepository(db))


@router.get("", response_model=CompanyRead)
async def get_company(company: CurrentCompany) -> CompanyRead:
    return CompanyRead.model_validate(company)


@router.patch("", response_model=CompanyRead)
async def update_company(
    data: CompanyUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: CompanyService = Depends(_get_service),
) -> CompanyRead:
    updated = await service.update(company, data)
    return CompanyRead.model_validate(updated)


# ─────────────────────────────────────────────────────────────────────
# Image uploads — logo, banner, gallery
# ─────────────────────────────────────────────────────────────────────
# Each endpoint stores the file under uploads/<subdir>/, sets the
# matching column on the company, and returns the refreshed company
# row so the dashboard editor can show the new URL immediately.

@router.post("/upload/logo", response_model=CompanyRead)
async def upload_logo(
    company: CurrentCompany,
    _user: CurrentUser,
    file: UploadFile = File(...),
    service: CompanyService = Depends(_get_service),
) -> CompanyRead:
    new_url = await company_logo_storage.save(file)
    # Best-effort: get rid of the previous file so we don't leak disk.
    company_logo_storage.delete(company.logo_url)
    updated = await service.update(company, CompanyUpdate(logo_url=new_url))
    return CompanyRead.model_validate(updated)


@router.post("/upload/banner", response_model=CompanyRead)
async def upload_banner(
    company: CurrentCompany,
    _user: CurrentUser,
    file: UploadFile = File(...),
    service: CompanyService = Depends(_get_service),
) -> CompanyRead:
    new_url = await company_banner_storage.save(file)
    company_banner_storage.delete(company.banner_url)
    updated = await service.update(company, CompanyUpdate(banner_url=new_url))
    return CompanyRead.model_validate(updated)


@router.delete("/upload/logo", response_model=CompanyRead)
async def remove_logo(
    company: CurrentCompany,
    _user: CurrentUser,
    service: CompanyService = Depends(_get_service),
) -> CompanyRead:
    company_logo_storage.delete(company.logo_url)
    updated = await service.update(company, CompanyUpdate(logo_url=None))
    return CompanyRead.model_validate(updated)


@router.delete("/upload/banner", response_model=CompanyRead)
async def remove_banner(
    company: CurrentCompany,
    _user: CurrentUser,
    service: CompanyService = Depends(_get_service),
) -> CompanyRead:
    company_banner_storage.delete(company.banner_url)
    updated = await service.update(company, CompanyUpdate(banner_url=None))
    return CompanyRead.model_validate(updated)


@router.post("/upload/gallery", response_model=CompanyRead)
async def upload_gallery_item(
    company: CurrentCompany,
    _user: CurrentUser,
    file: UploadFile = File(...),
    service: CompanyService = Depends(_get_service),
) -> CompanyRead:
    new_url = await company_gallery_storage.save(file)
    next_gallery = [*(company.gallery or []), {"url": new_url, "caption": None}]
    # Run the new list through the pydantic schema once to enforce shape.
    validated = [GalleryItem.model_validate(item).model_dump() for item in next_gallery]
    updated = await service.update(company, CompanyUpdate(gallery=validated))
    return CompanyRead.model_validate(updated)


@router.delete("/upload/gallery/{index}", response_model=CompanyRead)
async def remove_gallery_item(
    index: int,
    company: CurrentCompany,
    _user: CurrentUser,
    service: CompanyService = Depends(_get_service),
) -> CompanyRead:
    gallery = list(company.gallery or [])
    if index < 0 or index >= len(gallery):
        raise NotFoundError("Pozycja galerii nie istnieje.")
    removed = gallery.pop(index)
    if isinstance(removed, dict):
        company_gallery_storage.delete(removed.get("url"))
    updated = await service.update(company, CompanyUpdate(gallery=gallery))
    return CompanyRead.model_validate(updated)
