import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.tags.repository import TagRepository
from app.modules.tags.schemas import TagAssign, TagCreate, TagRead
from app.modules.tags.service import TagService

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> TagService:
    return TagService(TagRepository(db))


@router.post("", response_model=TagRead, status_code=201)
async def create_tag(
    data: TagCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: TagService = Depends(_get_service),
) -> TagRead:
    tag = await service.create(company.id, data)
    return TagRead.model_validate(tag)


@router.get("", response_model=list[TagRead])
async def list_tags(
    company: CurrentCompany,
    _user: CurrentUser,
    service: TagService = Depends(_get_service),
) -> list[TagRead]:
    tags = await service.list_by_company(company.id)
    return [TagRead.model_validate(t) for t in tags]


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: TagService = Depends(_get_service),
) -> Response:
    await service.delete(tag_id, company.id)
    return Response(status_code=204)


@router.post("/applications/{application_id}/tags", status_code=204)
async def assign_tag(
    application_id: uuid.UUID,
    data: TagAssign,
    company: CurrentCompany,
    _user: CurrentUser,
    service: TagService = Depends(_get_service),
) -> Response:
    await service.assign_tag(application_id, data.tag_id, company.id)
    return Response(status_code=204)


@router.delete("/applications/{application_id}/tags/{tag_id}", status_code=204)
async def remove_tag(
    application_id: uuid.UUID,
    tag_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: TagService = Depends(_get_service),
) -> Response:
    await service.remove_tag(application_id, tag_id, company.id)
    return Response(status_code=204)


@router.get("/applications/{application_id}/tags", response_model=list[TagRead])
async def get_application_tags(
    application_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: TagService = Depends(_get_service),
) -> list[TagRead]:
    tags = await service.get_application_tags(application_id, company.id)
    return [TagRead.model_validate(t) for t in tags]
