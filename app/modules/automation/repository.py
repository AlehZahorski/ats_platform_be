from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.automation.models import AutomationRule
from app.modules.automation.schemas import AutomationRuleCreate, AutomationRuleUpdate


class AutomationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, company_id: uuid.UUID, data: AutomationRuleCreate) -> AutomationRule:
        rule = AutomationRule(company_id=company_id, **data.model_dump())
        self.db.add(rule)
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    async def get_by_id(self, rule_id: uuid.UUID, company_id: uuid.UUID) -> Optional[AutomationRule]:
        result = await self.db.execute(
            select(AutomationRule).where(
                AutomationRule.id == rule_id,
                AutomationRule.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def list(self, company_id: uuid.UUID) -> list[AutomationRule]:
        result = await self.db.execute(
            select(AutomationRule)
            .where(AutomationRule.company_id == company_id)
            .order_by(AutomationRule.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_matching_rules(
        self,
        company_id: uuid.UUID,
        trigger_type: str,
        trigger_value: Optional[str] = None,
    ) -> list[AutomationRule]:
        """Fetch active rules matching the given trigger."""
        query = select(AutomationRule).where(
            AutomationRule.company_id == company_id,
            AutomationRule.trigger_type == trigger_type,
            AutomationRule.is_active.is_(True),
            AutomationRule.template_id.isnot(None),
        )
        if trigger_value:
            query = query.where(AutomationRule.trigger_value == trigger_value)

        result = await self.db.execute(
            query.options(selectinload(AutomationRule.template))
        )
        return list(result.scalars().all())

    async def update(self, rule: AutomationRule, data: AutomationRuleUpdate) -> AutomationRule:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(rule, field, value)
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    async def delete(self, rule: AutomationRule) -> None:
        await self.db.delete(rule)
        await self.db.flush()