
import uuid

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.tags.repository import TagRepository
from app.modules.tags.schemas import TagAssign, TagCreate, TagRead

router = APIRouter()


def _repo(db: AsyncSession = Depends(get_db)) -> TagRepository:
    return TagRepository(db)


@router.post("", response_model=TagRead, status_code=201)
async def create_tag(
    data: TagCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: TagRepository = Depends(_repo),
) -> TagRead:
    tag = await repo.create(company.id, data)
    return TagRead.model_validate(tag)


@router.get("", response_model=list[TagRead])
async def list_tags(
    company: CurrentCompany,
    _user: CurrentUser,
    repo: TagRepository = Depends(_repo),
) -> list[TagRead]:
    tags = await repo.list(company.id)
    return [TagRead.model_validate(t) for t in tags]


@router.post("/applications/{application_id}/tags")
async def assign_tag(
    application_id: uuid.UUID,
    data: TagAssign,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: TagRepository = Depends(_repo),
) -> Response:
    tag = await repo.get_by_id(data.tag_id, company.id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await repo.assign_tag(application_id, data.tag_id)
    return Response(status_code=204)


@router.delete("/applications/{application_id}/tags/{tag_id}")
async def remove_tag(
    application_id: uuid.UUID,
    tag_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: TagRepository = Depends(_repo),
) -> Response:
    await repo.remove_tag(application_id, tag_id)
    return Response(status_code=204)


@router.get("/applications/{application_id}/tags", response_model=list[TagRead])
async def get_application_tags(
    application_id: uuid.UUID,
    _company: CurrentCompany,
    _user: CurrentUser,
    repo: TagRepository = Depends(_repo),
) -> list[TagRead]:
    tags = await repo.get_application_tags(application_id)
    return [TagRead.model_validate(t) for t in tags]
