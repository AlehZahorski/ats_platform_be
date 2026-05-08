import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.audit.service import AuditService
from app.modules.notes.repository import NoteRepository
from app.modules.notes.schemas import NoteCreate, NoteRead
from app.modules.notes.service import NoteService

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> NoteService:
    return NoteService(NoteRepository(db), AuditService(db))


@router.post("/applications/{application_id}/notes", response_model=NoteRead, status_code=201)
async def add_note(
    application_id: uuid.UUID,
    data: NoteCreate,
    company: CurrentCompany,
    user: CurrentUser,
    service: NoteService = Depends(_get_service),
) -> NoteRead:
    note = await service.add_note(application_id, user.id, company.id, data)
    return NoteRead.model_validate(note)


@router.get("/applications/{application_id}/notes", response_model=list[NoteRead])
async def list_notes(
    application_id: uuid.UUID,
    _company: CurrentCompany,
    _user: CurrentUser,
    service: NoteService = Depends(_get_service),
) -> list[NoteRead]:
    notes = await service.list_by_application(application_id)
    return [NoteRead.model_validate(n) for n in notes]
