from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NoteCreate(BaseModel):
    content: str
    visible_to_candidate: bool = False


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    application_id: uuid.UUID
    author_id: uuid.UUID | None
    content: str
    visible_to_candidate: bool
    created_at: datetime
