
import uuid

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser, require_roles
from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import AuditLogList, AuditLogRead

router = APIRouter()


def _repo(db: AsyncSession = Depends(get_db)) -> AuditRepository:
    return AuditRepository(db)


@router.get(
    "",
    response_model=AuditLogList,
    dependencies=[Depends(require_roles("owner", "manager"))],
)
async def list_audit_logs(
    company: CurrentCompany,
    _user: CurrentUser,
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[uuid.UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    repo: AuditRepository = Depends(_repo),
) -> AuditLogList:
    logs, total = await repo.list(
        company_id=company.id,
        entity_type=entity_type,
        entity_id=entity_id,
        skip=skip,
        limit=limit,
    )
    return AuditLogList(
        items=[AuditLogRead.model_validate(log) for log in logs],
        total=total,
    )
