from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.core.enums.automation import AutomationTriggerType


class AutomationRuleCreate(BaseModel):
    name: str
    trigger_type: AutomationTriggerType
    trigger_value: Optional[str] = None
    template_id: Optional[uuid.UUID] = None
    is_active: bool = True


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    trigger_type: Optional[AutomationTriggerType] = None
    trigger_value: Optional[str] = None
    template_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None


class AutomationRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    trigger_type: AutomationTriggerType
    trigger_value: Optional[str]
    template_id: Optional[uuid.UUID]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AutomationTriggerPayload(BaseModel):
    trigger_type: AutomationTriggerType
    trigger_value: Optional[str] = None
    application_id: uuid.UUID
    company_id: uuid.UUID
    variables: dict = {}
