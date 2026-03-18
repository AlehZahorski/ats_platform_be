from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ConsentCreate(BaseModel):
    name: str
    content: str
    language: str = "en"
    required: bool = True


class ConsentUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    language: Optional[str] = None
    required: Optional[bool] = None
    is_active: Optional[bool] = None


class ConsentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    content: str
    language: str
    required: bool
    is_active: bool
    created_at: datetime


class ApplicationConsentCreate(BaseModel):
    consent_id: uuid.UUID
    accepted: bool


class ApplicationConsentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    application_id: uuid.UUID
    consent_id: uuid.UUID
    accepted: bool
    accepted_at: datetime
    consent: Optional[ConsentRead] = None


class DataRetentionUpdate(BaseModel):
    data_retention_until: Optional[datetime] = None


class AnonymizeResult(BaseModel):
    application_id: uuid.UUID
    anonymized: bool
    message: str