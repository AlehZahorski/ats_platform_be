from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.candidates.models import (
    Candidate,
    CandidateRefreshToken,
    SavedCompany,
    SavedJob,
    SavedSearch,
    SearchLog,
)


class CandidateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_email(self, email: str) -> Candidate | None:
        result = await self.db.execute(select(Candidate).where(Candidate.email == email.lower()))
        return result.scalar_one_or_none()

    async def get_by_id(self, candidate_id: uuid.UUID) -> Candidate | None:
        result = await self.db.execute(select(Candidate).where(Candidate.id == candidate_id))
        return result.scalar_one_or_none()

    async def create(self, *, email: str, password_hash: str, full_name: str | None) -> Candidate:
        candidate = Candidate(email=email.lower(), password_hash=password_hash, full_name=full_name)
        self.db.add(candidate)
        await self.db.flush()
        await self.db.refresh(candidate)
        return candidate

    async def save_refresh_token(
        self, candidate_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> None:
        self.db.add(
            CandidateRefreshToken(
                candidate_id=candidate_id, token_hash=token_hash, expires_at=expires_at
            )
        )
        await self.db.flush()

    async def get_refresh(self, token_hash: str) -> CandidateRefreshToken | None:
        result = await self.db.execute(
            select(CandidateRefreshToken).where(
                CandidateRefreshToken.token_hash == token_hash,
                CandidateRefreshToken.revoked.is_(False),
                CandidateRefreshToken.expires_at > datetime.now(UTC),
            )
        )
        return result.scalar_one_or_none()

    async def revoke_refresh(self, token_hash: str) -> None:
        await self.db.execute(
            update(CandidateRefreshToken)
            .where(CandidateRefreshToken.token_hash == token_hash)
            .values(revoked=True)
        )

    async def revoke_all(self, candidate_id: uuid.UUID) -> None:
        await self.db.execute(
            update(CandidateRefreshToken)
            .where(CandidateRefreshToken.candidate_id == candidate_id)
            .values(revoked=True)
        )


class SavedJobRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_candidate(self, candidate_id: uuid.UUID) -> list[SavedJob]:
        result = await self.db.execute(
            select(SavedJob)
            .where(SavedJob.candidate_id == candidate_id)
            .order_by(SavedJob.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, candidate_id: uuid.UUID, job_id: uuid.UUID) -> SavedJob | None:
        result = await self.db.execute(
            select(SavedJob).where(SavedJob.candidate_id == candidate_id, SavedJob.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def add(self, candidate_id: uuid.UUID, job_id: uuid.UUID) -> SavedJob:
        existing = await self.get(candidate_id, job_id)
        if existing:
            return existing
        sj = SavedJob(candidate_id=candidate_id, job_id=job_id)
        self.db.add(sj)
        await self.db.flush()
        await self.db.refresh(sj)
        return sj

    async def remove(self, candidate_id: uuid.UUID, job_id: uuid.UUID) -> None:
        existing = await self.get(candidate_id, job_id)
        if existing:
            await self.db.delete(existing)
            await self.db.flush()


class SavedCompanyRepository:
    """Mirrors SavedJobRepository — same shape, different FK. Lets us reuse
    the toggle-style UX (POST = add, DELETE = remove) on the frontend."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_candidate(self, candidate_id: uuid.UUID) -> list[SavedCompany]:
        result = await self.db.execute(
            select(SavedCompany)
            .where(SavedCompany.candidate_id == candidate_id)
            .order_by(SavedCompany.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, candidate_id: uuid.UUID, company_id: uuid.UUID) -> SavedCompany | None:
        result = await self.db.execute(
            select(SavedCompany).where(
                SavedCompany.candidate_id == candidate_id, SavedCompany.company_id == company_id
            )
        )
        return result.scalar_one_or_none()

    async def add(self, candidate_id: uuid.UUID, company_id: uuid.UUID) -> SavedCompany:
        existing = await self.get(candidate_id, company_id)
        if existing:
            return existing
        sc = SavedCompany(candidate_id=candidate_id, company_id=company_id)
        self.db.add(sc)
        await self.db.flush()
        await self.db.refresh(sc)
        return sc

    async def remove(self, candidate_id: uuid.UUID, company_id: uuid.UUID) -> None:
        existing = await self.get(candidate_id, company_id)
        if existing:
            await self.db.delete(existing)
            await self.db.flush()


class SavedSearchRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_candidate(self, candidate_id: uuid.UUID) -> list[SavedSearch]:
        result = await self.db.execute(
            select(SavedSearch)
            .where(SavedSearch.candidate_id == candidate_id)
            .order_by(SavedSearch.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(
        self, candidate_id: uuid.UUID, name: str, query: dict, notify_email: bool
    ) -> SavedSearch:
        ss = SavedSearch(
            candidate_id=candidate_id, name=name, query=query, notify_email=notify_email
        )
        self.db.add(ss)
        await self.db.flush()
        await self.db.refresh(ss)
        return ss

    async def delete(self, candidate_id: uuid.UUID, search_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(SavedSearch).where(
                SavedSearch.id == search_id, SavedSearch.candidate_id == candidate_id
            )
        )
        ss = result.scalar_one_or_none()
        if not ss:
            return False
        await self.db.delete(ss)
        await self.db.flush()
        return True


class SearchLogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(
        self,
        *,
        candidate_id: uuid.UUID | None,
        query_text: str | None,
        category: str | None,
        location: str | None,
    ) -> None:
        # Skip writing empty searches — they are noise.
        if not (query_text or category or location):
            return
        self.db.add(
            SearchLog(
                candidate_id=candidate_id,
                query_text=query_text[:200] if query_text else None,
                category=category,
                location=location,
            )
        )
        await self.db.flush()
