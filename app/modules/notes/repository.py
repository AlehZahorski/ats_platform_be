from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notes.models import Note
from app.modules.notes.schemas import NoteCreate


class NoteRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, application_id: uuid.UUID, author_id: uuid.UUID, data: NoteCreate) -> Note:
        note = Note(application_id=application_id, author_id=author_id, **data.model_dump())
        self.db.add(note)
        await self.db.flush()
        await self.db.refresh(note)
        return note

    async def list(self, application_id: uuid.UUID) -> list[Note]:
        result = await self.db.execute(
            select(Note)
            .where(Note.application_id == application_id)
            .order_by(Note.created_at.asc())
        )
        return list(result.scalars().all())
