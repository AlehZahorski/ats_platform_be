from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Auth ────────────────────────────────────────────────────────────────────
class CandidateSignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class CandidateLoginRequest(BaseModel):
    email: EmailStr
    password: str


# ── Profile ─────────────────────────────────────────────────────────────────
class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    avatar_key: str | None
    phone: str | None
    location: str | None
    headline: str | None
    language: str
    is_verified: bool
    created_at: datetime


class CandidateUpdate(BaseModel):
    full_name: str | None = None
    avatar_key: str | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    language: str | None = None


# ── Saved jobs ──────────────────────────────────────────────────────────────
class SavedJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    created_at: datetime


# ── Saved companies ─────────────────────────────────────────────────────────
class SavedCompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID
    created_at: datetime


# ── Saved searches ──────────────────────────────────────────────────────────
class SavedSearchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    query: dict[str, Any] = Field(default_factory=dict)
    notify_email: bool = True


class SavedSearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    query: dict[str, Any]
    notify_email: bool
    created_at: datetime


# ── Search log ──────────────────────────────────────────────────────────────
class SearchLogCreate(BaseModel):
    query_text: str | None = None
    category: str | None = None
    location: str | None = None
