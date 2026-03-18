from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EmailTemplateCreate(BaseModel):
    name: str
    type: str
    subject: str
    body: str
    language: str = "en"
    variables: dict[str, Any] | None = None


class EmailTemplateUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    subject: str | None = None
    body: str | None = None
    language: str | None = None
    variables: dict[str, Any] | None = None


class EmailTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    type: str
    subject: str
    body: str
    language: str
    variables: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class EmailTemplatePreview(BaseModel):
    subject: str
    body: str