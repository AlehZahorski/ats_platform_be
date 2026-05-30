"""Admin AI-usage analytics service (F-23).

Aggregates ``api_usage_logs`` across ALL tenants (admin-only — no company
scoping, unlike app/modules/llm_usage which is per-recruiter) into a
per-company / per-operation / per-model cost + token report.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admins.usage_schemas import (
    AdminUsageReport,
    CompanyUsageRow,
    ModelUsageRow,
    OperationUsageRow,
    RecentUsageRow,
    UsageOverview,
)
from app.modules.applications.models import ApiUsageLog
from app.modules.companies.models import Company


class AdminUsageService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def usage_report(
        self, *, days: int | None = 30, recent_limit: int = 50
    ) -> AdminUsageReport:
        """Build the admin usage report.

        ``days`` bounds a rolling window from now; ``None`` means all-time.
        Token/cost sums are coalesced to 0 so a company with only token-less
        rows still appears with calls > 0.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
            if days is not None
            else None
        )

        def _scoped(stmt):
            return stmt.where(ApiUsageLog.created_at >= cutoff) if cutoff is not None else stmt

        # Reusable aggregate expressions.
        calls = func.count(ApiUsageLog.id)
        inp = func.coalesce(func.sum(ApiUsageLog.input_tokens), 0)
        out = func.coalesce(func.sum(ApiUsageLog.output_tokens), 0)
        total = func.coalesce(
            func.sum(ApiUsageLog.input_tokens + ApiUsageLog.output_tokens), 0
        )
        cost = func.coalesce(func.sum(ApiUsageLog.cost_usd), 0)

        # 1. Overview.
        ov = (
            await self.db.execute(
                _scoped(
                    select(
                        calls, inp, out, total, cost,
                        func.count(func.distinct(ApiUsageLog.company_id)),
                    )
                )
            )
        ).one()
        overview = UsageOverview(
            total_calls=ov[0] or 0,
            total_input_tokens=int(ov[1] or 0),
            total_output_tokens=int(ov[2] or 0),
            total_tokens=int(ov[3] or 0),
            total_cost_usd=float(ov[4] or 0),
            companies_using=ov[5] or 0,
            period_days=days,
        )

        # 2. By company (join for the display name).
        company_rows = (
            await self.db.execute(
                _scoped(
                    select(
                        ApiUsageLog.company_id,
                        Company.name,
                        calls, inp, out, total, cost,
                        func.max(ApiUsageLog.created_at),
                    )
                    .join(Company, Company.id == ApiUsageLog.company_id)
                    .group_by(ApiUsageLog.company_id, Company.name)
                    .order_by(cost.desc())
                )
            )
        ).all()
        by_company = [
            CompanyUsageRow(
                company_id=r[0],
                company_name=r[1],
                calls=r[2] or 0,
                input_tokens=int(r[3] or 0),
                output_tokens=int(r[4] or 0),
                total_tokens=int(r[5] or 0),
                cost_usd=float(r[6] or 0),
                last_used_at=r[7],
            )
            for r in company_rows
        ]

        # 3. By operation.
        op_rows = (
            await self.db.execute(
                _scoped(
                    select(ApiUsageLog.operation, calls, total, cost)
                    .group_by(ApiUsageLog.operation)
                    .order_by(cost.desc())
                )
            )
        ).all()
        by_operation = [
            OperationUsageRow(
                operation=r[0],
                calls=r[1] or 0,
                total_tokens=int(r[2] or 0),
                cost_usd=float(r[3] or 0),
            )
            for r in op_rows
        ]

        # 4. By model.
        model_rows = (
            await self.db.execute(
                _scoped(
                    select(ApiUsageLog.llm_model, calls, total, cost)
                    .group_by(ApiUsageLog.llm_model)
                    .order_by(cost.desc())
                )
            )
        ).all()
        by_model = [
            ModelUsageRow(
                llm_model=r[0],
                calls=r[1] or 0,
                total_tokens=int(r[2] or 0),
                cost_usd=float(r[3] or 0),
            )
            for r in model_rows
        ]

        # 5. Recent calls (newest first).
        recent_rows = (
            await self.db.execute(
                _scoped(
                    select(ApiUsageLog, Company.name)
                    .join(Company, Company.id == ApiUsageLog.company_id)
                    .order_by(ApiUsageLog.created_at.desc())
                    .limit(recent_limit)
                )
            )
        ).all()
        recent = [
            RecentUsageRow(
                id=log.id,
                company_id=log.company_id,
                company_name=name,
                operation=log.operation,
                llm_model=log.llm_model,
                prompt_name=log.prompt_name,
                input_tokens=int(log.input_tokens or 0),
                output_tokens=int(log.output_tokens or 0),
                total_tokens=int((log.input_tokens or 0) + (log.output_tokens or 0)),
                cost_usd=float(log.cost_usd or 0),
                created_at=log.created_at,
            )
            for log, name in recent_rows
        ]

        return AdminUsageReport(
            overview=overview,
            by_company=by_company,
            by_operation=by_operation,
            by_model=by_model,
            recent=recent,
        )
