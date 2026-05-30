"""Admin AI-usage analytics schemas (F-23).

Shapes the cross-tenant view the admin panel renders from ``api_usage_logs``.
Field names mirror the ORM model (``input_tokens`` / ``output_tokens`` /
``llm_model`` / ``operation``); ``total_tokens`` is derived (input + output).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class UsageOverview(BaseModel):
    """Platform-wide totals for the selected window."""
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost_usd: float
    companies_using: int
    period_days: int | None = None  # None == all time


class CompanyUsageRow(BaseModel):
    company_id: uuid.UUID
    company_name: str
    calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    last_used_at: datetime | None = None


class OperationUsageRow(BaseModel):
    operation: str
    calls: int
    total_tokens: int
    cost_usd: float


class ModelUsageRow(BaseModel):
    llm_model: str | None = None
    calls: int
    total_tokens: int
    cost_usd: float


class RecentUsageRow(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    company_name: str
    operation: str
    llm_model: str | None = None
    prompt_name: str | None = None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    created_at: datetime


class AdminUsageReport(BaseModel):
    overview: UsageOverview
    by_company: list[CompanyUsageRow]
    by_operation: list[OperationUsageRow]
    by_model: list[ModelUsageRow]
    recent: list[RecentUsageRow]
