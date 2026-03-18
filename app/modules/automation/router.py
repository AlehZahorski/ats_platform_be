import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.automation.schemas import (
    AutomationRuleCreate,
    AutomationRuleRead,
    AutomationRuleUpdate,
)
from app.modules.automation.service import AutomationService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> AutomationService:
    return AutomationService(db)


@router.post("", response_model=AutomationRuleRead, status_code=201)
async def create_rule(
    data: AutomationRuleCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: AutomationService = Depends(_svc),
) -> AutomationRuleRead:
    rule = await svc.create(company.id, data)
    return AutomationRuleRead.model_validate(rule)


@router.get("", response_model=list[AutomationRuleRead])
async def list_rules(
    company: CurrentCompany,
    _user: CurrentUser,
    svc: AutomationService = Depends(_svc),
) -> list[AutomationRuleRead]:
    rules = await svc.list(company.id)
    return [AutomationRuleRead.model_validate(r) for r in rules]


@router.get("/{rule_id}", response_model=AutomationRuleRead)
async def get_rule(
    rule_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: AutomationService = Depends(_svc),
) -> AutomationRuleRead:
    rule = await svc.get(rule_id, company.id)
    return AutomationRuleRead.model_validate(rule)


@router.patch("/{rule_id}", response_model=AutomationRuleRead)
async def update_rule(
    rule_id: uuid.UUID,
    data: AutomationRuleUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: AutomationService = Depends(_svc),
) -> AutomationRuleRead:
    rule = await svc.update(rule_id, company.id, data)
    return AutomationRuleRead.model_validate(rule)


@router.post("/{rule_id}/toggle", response_model=AutomationRuleRead)
async def toggle_rule(
    rule_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: AutomationService = Depends(_svc),
) -> AutomationRuleRead:
    rule = await svc.toggle(rule_id, company.id)
    return AutomationRuleRead.model_validate(rule)


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: AutomationService = Depends(_svc),
) -> Response:
    await svc.delete(rule_id, company.id)
    return Response(status_code=204)