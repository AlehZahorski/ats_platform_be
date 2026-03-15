
import uuid

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.audit.service import AuditService
from app.modules.notes.repository import NoteRepository
from app.modules.notes.schemas import NoteCreate, NoteRead

router = APIRouter()


def _repo(db: AsyncSession = Depends(get_db)) -> NoteRepository:
    return NoteRepository(db)


@router.post("/applications/{application_id}/notes", response_model=NoteRead, status_code=201)
async def add_note(
    application_id: uuid.UUID,
    data: NoteCreate,
    company: CurrentCompany,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    repo: NoteRepository = Depends(_repo),
) -> NoteRead:
    note = await repo.create(application_id, user.id, data)

    audit = AuditService(db)
    await audit.log(
        company_id=company.id,
        user_id=user.id,
        action="note_added",
        entity_type="application",
        entity_id=application_id,
    )

    return NoteRead.model_validate(note)


@router.get("/applications/{application_id}/notes", response_model=list[NoteRead])
async def list_notes(
    application_id: uuid.UUID,
    _company: CurrentCompany,
    _user: CurrentUser,
    repo: NoteRepository = Depends(_repo),
) -> list[NoteRead]:
    notes = await repo.list(application_id)
    return [NoteRead.model_validate(n) for n in notes]
