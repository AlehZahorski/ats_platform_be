"""LLM usage dashboard (audit F-17).

Reads from ``api_usage_logs`` and returns per-day / per-model / per-prompt
aggregates for the calling company. Authentication is the standard HR
company-scope dependency — recruiters see only their own spend.

Two endpoints:
- ``GET /summary?days=30`` — list of buckets sorted by day desc.
- ``GET /budget`` — current rolling-24h spend and the configured budget.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.core.rate_limit import rate_limit
from app.modules.applications.repository import ApplicationRepository

router = APIRouter()


@router.get("/summary", dependencies=[Depends(rate_limit("60/minute"))])
async def llm_usage_summary(
    request: Request,
    company: CurrentCompany,
    _user: CurrentUser,
    days: int = Query(default=30, ge=1, le=180),
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ApplicationRepository(db)
    buckets = await repo.llm_usage_summary(company.id, days=days)
    return {
        "days": days,
        "rows": [
            {
                **row,
                "day": row["day"].isoformat() if row["day"] else None,
            }
            for row in buckets
        ],
    }


@router.get("/budget", dependencies=[Depends(rate_limit("60/minute"))])
async def llm_budget(
    request: Request,
    company: CurrentCompany,
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ApplicationRepository(db)
    spent = await repo.sum_llm_cost_last_24h(company.id)
    budget = settings.llm_daily_budget_usd_per_company
    return {
        "budget_usd": budget,
        "spent_last_24h_usd": round(spent, 4),
        "remaining_usd": round(max(0.0, budget - spent), 4) if budget > 0 else None,
        "exceeded": budget > 0 and spent >= budget,
    }
