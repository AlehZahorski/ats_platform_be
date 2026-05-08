import uuid

from fastapi import APIRouter, Depends, Response
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
from app.modules.forms.service import FormService

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> FormService:
    return FormService(FormRepository(db))


@router.post("/templates", response_model=FormTemplateRead, status_code=201)
async def create_template(
    data: FormTemplateCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: FormService = Depends(_get_service),
) -> FormTemplateRead:
    template = await service.create_template(company.id, data)
    return FormTemplateRead.model_validate(template)


@router.get("/templates", response_model=list[FormTemplateRead])
async def list_templates(
    company: CurrentCompany,
    _user: CurrentUser,
    service: FormService = Depends(_get_service),
) -> list[FormTemplateRead]:
    templates = await service.list_templates(company.id)
    return [FormTemplateRead.model_validate(t) for t in templates]


@router.get("/templates/{template_id}", response_model=FormTemplateRead)
async def get_template(
    template_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: FormService = Depends(_get_service),
) -> FormTemplateRead:
    template = await service.get_template(template_id, company.id)
    return FormTemplateRead.model_validate(template)


@router.patch("/templates/{template_id}", response_model=FormTemplateRead)
async def update_template(
    template_id: uuid.UUID,
    data: FormTemplateUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: FormService = Depends(_get_service),
) -> FormTemplateRead:
    template = await service.update_template(template_id, company.id, data)
    return FormTemplateRead.model_validate(template)


@router.post("/templates/{template_id}/fields", response_model=FormFieldRead, status_code=201)
async def add_field(
    template_id: uuid.UUID,
    data: FormFieldCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: FormService = Depends(_get_service),
) -> FormFieldRead:
    field = await service.add_field(template_id, company.id, data)
    return FormFieldRead.model_validate(field)


@router.delete("/templates/{template_id}/fields/{field_id}", status_code=204)
async def delete_field(
    template_id: uuid.UUID,
    field_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: FormService = Depends(_get_service),
) -> Response:
    await service.delete_field(template_id, field_id, company.id)
    return Response(status_code=204)
