from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums.automation import AutomationTriggerType


class AutomationRuleCreate(BaseModel):
    name: str
    trigger_type: AutomationTriggerType
    trigger_value: str | None = None
    template_id: uuid.UUID | None = None
    is_active: bool = True


class AutomationRuleUpdate(BaseModel):
    name: str | None = None
    trigger_type: AutomationTriggerType | None = None
    trigger_value: str | None = None
    template_id: uuid.UUID | None = None
    is_active: bool | None = None


class AutomationRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    trigger_type: AutomationTriggerType
    trigger_value: str | None
    template_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AutomationTriggerPayload(BaseModel):
    trigger_type: AutomationTriggerType
    trigger_value: str | None = None
    application_id: uuid.UUID
    company_id: uuid.UUID
    variables: dict = {}
