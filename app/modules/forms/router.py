
import uuid

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.forms.repository import FormRepository
from app.modules.forms.schemas import (
    FormFieldCreate,
    FormFieldRead,
    FormTemplateCreate,
    FormTemplateRead,
    FormTemplateUpdate,
)

router = APIRouter()


def _repo(db: AsyncSession = Depends(get_db)) -> FormRepository:
    return FormRepository(db)


@router.post("/templates", response_model=FormTemplateRead, status_code=201)
async def create_template(
    data: FormTemplateCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: FormRepository = Depends(_repo),
) -> FormTemplateRead:
    template = await repo.create_template(company.id, data)
    return FormTemplateRead.model_validate(template)


@router.get("/templates", response_model=list[FormTemplateRead])
async def list_templates(
    company: CurrentCompany,
    _user: CurrentUser,
    repo: FormRepository = Depends(_repo),
) -> list[FormTemplateRead]:
    templates = await repo.list(company.id)
    return [FormTemplateRead.model_validate(t) for t in templates]


@router.get("/templates/{template_id}", response_model=FormTemplateRead)
async def get_template(
    template_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: FormRepository = Depends(_repo),
) -> FormTemplateRead:
    template = await repo.get_by_id(template_id, company.id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return FormTemplateRead.model_validate(template)


@router.patch("/templates/{template_id}", response_model=FormTemplateRead)
async def update_template(
    template_id: uuid.UUID,
    data: FormTemplateUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: FormRepository = Depends(_repo),
) -> FormTemplateRead:
    template = await repo.get_by_id(template_id, company.id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    updated = await repo.update(template, data)
    return FormTemplateRead.model_validate(updated)


@router.post("/templates/{template_id}/fields", response_model=FormFieldRead, status_code=201)
async def add_field(
    template_id: uuid.UUID,
    data: FormFieldCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: FormRepository = Depends(_repo),
) -> FormFieldRead:
    template = await repo.get_by_id(template_id, company.id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    field = await repo.add_field(template_id, data)
    return FormFieldRead.model_validate(field)


@router.delete("/templates/{template_id}/fields/{field_id}")
async def delete_field(
    template_id: uuid.UUID,
    field_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: FormRepository = Depends(_repo),
) -> Response:
    template = await repo.get_by_id(template_id, company.id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    await repo.delete_field(field_id)
    return Response(status_code=204)
