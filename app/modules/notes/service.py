from __future__ import annotations

import uuid

from app.core.base_service import BaseService
from app.core.ownership import ensure_application_in_company
from app.modules.audit.service import AuditService
from app.modules.notes.models import Note
from app.modules.notes.repository import NoteRepository
from app.modules.notes.schemas import NoteCreate


class NoteService(BaseService[NoteRepository]):
    def __init__(self, repository: NoteRepository, audit: AuditService) -> None:
        super().__init__(repository)
        self.audit = audit

    async def add_note(
        self,
        application_id: uuid.UUID,
        author_id: uuid.UUID,
        company_id: uuid.UUID,
        data: NoteCreate,
    ) -> Note:
        await ensure_application_in_company(self.repository.db, application_id, company_id)
        note = await self.repository.create(application_id, author_id, data)
        await self.audit.log(
            company_id=company_id,
            user_id=author_id,
            action="note_added",
            entity_type="application",
            entity_id=application_id,
        )
        return note

    async def list_by_application(
        self, application_id: uuid.UUID, company_id: uuid.UUID
    ) -> list[Note]:
        await ensure_application_in_company(self.repository.db, application_id, company_id)
        return await self.repository.list_by_application(application_id)
