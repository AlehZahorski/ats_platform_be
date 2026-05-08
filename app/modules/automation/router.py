import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.automation.repository import AutomationRepository
from app.modules.automation.schemas import (
    AutomationRuleCreate,
    AutomationRuleRead,
    AutomationRuleUpdate,
)
from app.modules.automation.service import AutomationService

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> AutomationService:
    return AutomationService(AutomationRepository(db))


@router.post("", response_model=AutomationRuleRead, status_code=201)
async def create_rule(
    data: AutomationRuleCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: AutomationService = Depends(_get_service),
) -> AutomationRuleRead:
    rule = await service.create(company.id, data)
    return AutomationRuleRead.model_validate(rule)


@router.get("", response_model=list[AutomationRuleRead])
async def list_rules(
    company: CurrentCompany,
    _user: CurrentUser,
    service: AutomationService = Depends(_get_service),
) -> list[AutomationRuleRead]:
    rules = await service.list(company.id)
    return [AutomationRuleRead.model_validate(r) for r in rules]


@router.get("/{rule_id}", response_model=AutomationRuleRead)
async def get_rule(
    rule_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: AutomationService = Depends(_get_service),
) -> AutomationRuleRead:
    rule = await service.get(rule_id, company.id)
    return AutomationRuleRead.model_validate(rule)


@router.patch("/{rule_id}", response_model=AutomationRuleRead)
async def update_rule(
    rule_id: uuid.UUID,
    data: AutomationRuleUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: AutomationService = Depends(_get_service),
) -> AutomationRuleRead:
    rule = await service.update(rule_id, company.id, data)
    return AutomationRuleRead.model_validate(rule)


@router.post("/{rule_id}/toggle", response_model=AutomationRuleRead)
async def toggle_rule(
    rule_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: AutomationService = Depends(_get_service),
) -> AutomationRuleRead:
    rule = await service.toggle(rule_id, company.id)
    return AutomationRuleRead.model_validate(rule)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: AutomationService = Depends(_get_service),
) -> Response:
    await service.delete(rule_id, company.id)
    return Response(status_code=204)
