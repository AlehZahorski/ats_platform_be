import uuid
from typing import Optional, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.email_templates.schemas import (
    EmailTemplateCreate,
    EmailTemplatePreview,
    EmailTemplateRead,
    EmailTemplateUpdate,
)
from app.modules.email_templates.service import EmailTemplateService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> EmailTemplateService:
    return EmailTemplateService(db)


class PreviewRequest(BaseModel):
    variables: Optional[dict[str, Any]] = None


@router.post("", response_model=EmailTemplateRead, status_code=201)
async def create_template(
    data: EmailTemplateCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: EmailTemplateService = Depends(_svc),
) -> EmailTemplateRead:
    template = await svc.create(company.id, data)
    return EmailTemplateRead.model_validate(template)


@router.get("", response_model=list[EmailTemplateRead])
async def list_templates(
    company: CurrentCompany,
    _user: CurrentUser,
    language: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    svc: EmailTemplateService = Depends(_svc),
) -> list[EmailTemplateRead]:
    templates = await svc.list(company.id, language=language, type=type)
    return [EmailTemplateRead.model_validate(t) for t in templates]


@router.get("/{template_id}", response_model=EmailTemplateRead)
async def get_template(
    template_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: EmailTemplateService = Depends(_svc),
) -> EmailTemplateRead:
    template = await svc.get(template_id, company.id)
    return EmailTemplateRead.model_validate(template)


@router.patch("/{template_id}", response_model=EmailTemplateRead)
async def update_template(
    template_id: uuid.UUID,
    data: EmailTemplateUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: EmailTemplateService = Depends(_svc),
) -> EmailTemplateRead:
    template = await svc.update(template_id, company.id, data)
    return EmailTemplateRead.model_validate(template)


@router.delete("/{template_id}")
async def delete_template(
    template_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: EmailTemplateService = Depends(_svc),
) -> Response:
    await svc.delete(template_id, company.id)
    return Response(status_code=204)


@router.post("/{template_id}/preview", response_model=EmailTemplatePreview)
async def preview_template(
    template_id: uuid.UUID,
    data: PreviewRequest,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: EmailTemplateService = Depends(_svc),
) -> EmailTemplatePreview:
    return await svc.preview(template_id, company.id, data.variables)