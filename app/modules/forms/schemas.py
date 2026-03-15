from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

FieldType = Literal[
    "text", "textarea", "number", "email", "phone",
    "select", "multiselect", "checkbox", "file", "date",
]


class FormFieldCreate(BaseModel):
    label: str
    field_type: FieldType
    required: bool = False
    options: list[str] | None = None
    validation: dict[str, Any] | None = None
    order_index: int = 0


class FormFieldRead(FormFieldCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    template_id: uuid.UUID


class FormTemplateCreate(BaseModel):
    name: str
    fields: list[FormFieldCreate] = []


class FormTemplateUpdate(BaseModel):
    name: str | None = None


class FormTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    created_at: datetime
    fields: list[FormFieldRead] = []
