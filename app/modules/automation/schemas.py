from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AutomationRuleCreate(BaseModel):
    name: str
    trigger_type: str          # stage_changed | application_created
    trigger_value: Optional[str] = None   # stage_id for stage_changed
    template_id: Optional[uuid.UUID] = None
    is_active: bool = True


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_value: Optional[str] = None
    template_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None


class AutomationRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    trigger_type: str
    trigger_value: Optional[str]
    template_id: Optional[uuid.UUID]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AutomationTriggerPayload(BaseModel):
    """Internal payload used to trigger automation evaluation."""
    trigger_type: str
    trigger_value: Optional[str] = None
    application_id: uuid.UUID
    company_id: uuid.UUID
    variables: dict = {}