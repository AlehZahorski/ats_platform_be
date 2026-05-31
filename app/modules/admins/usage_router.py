"""Admin AI-usage analytics router (F-23).

Admin-only, cross-tenant view of ``api_usage_logs``. Distinct from
app/modules/llm_usage (which is company-scoped for recruiters) — here an
admin sees every company's token spend. Guarded by ``get_current_admin``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.admins.dependencies import get_current_admin
from app.modules.admins.models import Admin
from app.modules.admins.usage_schemas import AdminUsageReport
from app.modules.admins.usage_service import AdminUsageService

router = APIRouter()


def _service(db: AsyncSession = Depends(get_db)) -> AdminUsageService:
    return AdminUsageService(db)


@router.get("", response_model=AdminUsageReport)
async def admin_usage(
    _admin: Admin = Depends(get_current_admin),
    service: AdminUsageService = Depends(_service),
    days: int = Query(
        30,
        ge=0,
        le=365,
        description="Rolling lookback window in days. Pass 0 for all-time.",
    ),
) -> AdminUsageReport:
    """Per-company AI token usage and cost, plus breakdowns by operation/model
    and the most recent calls. ``days=0`` returns the all-time report."""
    return await service.usage_report(days=days or None)
