from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.base_repository import BaseRepository
from app.modules.notes.models import Note
from app.modules.notes.schemas import NoteCreate


class NoteRepository(BaseRepository[Note]):
    model = Note

    async def create(
        self, application_id: uuid.UUID, author_id: uuid.UUID, data: NoteCreate
    ) -> Note:
        note = Note(application_id=application_id, author_id=author_id, **data.model_dump())
        return await self.save(note)

    async def list_by_application(self, application_id: uuid.UUID) -> list[Note]:
        result = await self.db.execute(
            select(Note)
            .where(Note.application_id == application_id)
            .order_by(Note.created_at.asc())
        )
        return list(result.scalars().all())
