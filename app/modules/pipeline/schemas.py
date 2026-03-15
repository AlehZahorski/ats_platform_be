from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    order_index: int


class StageHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    application_id: uuid.UUID
    stage: StageRead
    changed_at: datetime
    changed_by: uuid.UUID | None


class UpdateStageRequest(BaseModel):
    stage_id: uuid.UUID
    notify_candidate: bool = False
