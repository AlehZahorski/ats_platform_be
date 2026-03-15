from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr


class SignupCompanyRequest(BaseModel):
    company_name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


class GoogleCallbackRequest(BaseModel):
    code: str
    state: str
