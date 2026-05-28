import uuid
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.candidates.dependencies import CurrentCandidate, OptionalCandidate
from app.modules.candidates.repository import (
    CandidateRepository,
    SavedCompanyRepository,
    SavedJobRepository,
    SavedSearchRepository,
    SearchLogRepository,
)
from app.modules.candidates.schemas import (
    CandidateLoginRequest,
    CandidateRead,
    CandidateSignupRequest,
    CandidateUpdate,
    SavedCompanyRead,
    SavedJobRead,
    SavedSearchCreate,
    SavedSearchRead,
    SearchLogCreate,
)
from app.modules.candidates.service import (
    CANDIDATE_REFRESH_COOKIE,
    CandidateAuthService,
)

router = APIRouter()


def _auth_service(db: AsyncSession = Depends(get_db)) -> CandidateAuthService:
    return CandidateAuthService(CandidateRepository(db))


# ─────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────
@router.post("/signup", response_model=CandidateRead, status_code=201)
async def signup(
    data: CandidateSignupRequest,
    response: Response,
    service: CandidateAuthService = Depends(_auth_service),
) -> CandidateRead:
    candidate = await service.signup(
        email=data.email, password=data.password, full_name=data.full_name, response=response,
    )
    return CandidateRead.model_validate(candidate)


@router.post("/login", response_model=CandidateRead)
async def login(
    data: CandidateLoginRequest,
    response: Response,
    service: CandidateAuthService = Depends(_auth_service),
) -> CandidateRead:
    candidate = await service.login(email=data.email, password=data.password, response=response)
    return CandidateRead.model_validate(candidate)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    candidate_refresh_token: Optional[str] = Cookie(default=None, alias=CANDIDATE_REFRESH_COOKIE),
    service: CandidateAuthService = Depends(_auth_service),
) -> Response:
    await service.logout(refresh_token=candidate_refresh_token, response=response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/refresh", response_model=CandidateRead)
async def refresh(
    response: Response,
    candidate_refresh_token: Optional[str] = Cookie(default=None, alias=CANDIDATE_REFRESH_COOKIE),
    service: CandidateAuthService = Depends(_auth_service),
) -> CandidateRead:
    if not candidate_refresh_token:
        from app.core.exceptions import UnauthorizedError
        raise UnauthorizedError("Brak sesji")
    candidate = await service.refresh(refresh_token=candidate_refresh_token, response=response)
    return CandidateRead.model_validate(candidate)


# ─────────────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────────────
@router.get("/me", response_model=CandidateRead)
async def get_me(candidate: CurrentCandidate) -> CandidateRead:
    return CandidateRead.model_validate(candidate)


@router.patch("/me", response_model=CandidateRead)
async def update_me(
    data: CandidateUpdate,
    candidate: CurrentCandidate,
    service: CandidateAuthService = Depends(_auth_service),
) -> CandidateRead:
    updated = await service.update_profile(candidate, data.model_dump(exclude_unset=True))
    return CandidateRead.model_validate(updated)


# ─────────────────────────────────────────────────────────────────────
# Saved jobs
# ─────────────────────────────────────────────────────────────────────
@router.get("/me/saved-jobs", response_model=list[SavedJobRead])
async def list_saved_jobs(
    candidate: CurrentCandidate,
    db: AsyncSession = Depends(get_db),
) -> list[SavedJobRead]:
    rows = await SavedJobRepository(db).list_for_candidate(candidate.id)
    return [SavedJobRead.model_validate(r) for r in rows]


@router.post("/me/saved-jobs/{job_id}", response_model=SavedJobRead, status_code=201)
async def save_job(
    job_id: uuid.UUID,
    candidate: CurrentCandidate,
    db: AsyncSession = Depends(get_db),
) -> SavedJobRead:
    sj = await SavedJobRepository(db).add(candidate.id, job_id)
    return SavedJobRead.model_validate(sj)


@router.delete("/me/saved-jobs/{job_id}", status_code=204)
async def unsave_job(
    job_id: uuid.UUID,
    candidate: CurrentCandidate,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await SavedJobRepository(db).remove(candidate.id, job_id)
    return Response(status_code=204)


# ─────────────────────────────────────────────────────────────────────
# Saved companies (Obserwuj firmę)
# ─────────────────────────────────────────────────────────────────────
@router.get("/me/saved-companies", response_model=list[SavedCompanyRead])
async def list_saved_companies(
    candidate: CurrentCandidate,
    db: AsyncSession = Depends(get_db),
) -> list[SavedCompanyRead]:
    rows = await SavedCompanyRepository(db).list_for_candidate(candidate.id)
    return [SavedCompanyRead.model_validate(r) for r in rows]


@router.post("/me/saved-companies/{company_id}", response_model=SavedCompanyRead, status_code=201)
async def save_company(
    company_id: uuid.UUID,
    candidate: CurrentCandidate,
    db: AsyncSession = Depends(get_db),
) -> SavedCompanyRead:
    sc = await SavedCompanyRepository(db).add(candidate.id, company_id)
    return SavedCompanyRead.model_validate(sc)


@router.delete("/me/saved-companies/{company_id}", status_code=204)
async def unsave_company(
    company_id: uuid.UUID,
    candidate: CurrentCandidate,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await SavedCompanyRepository(db).remove(candidate.id, company_id)
    return Response(status_code=204)


# ─────────────────────────────────────────────────────────────────────
# Saved searches
# ─────────────────────────────────────────────────────────────────────
@router.get("/me/saved-searches", response_model=list[SavedSearchRead])
async def list_saved_searches(
    candidate: CurrentCandidate,
    db: AsyncSession = Depends(get_db),
) -> list[SavedSearchRead]:
    rows = await SavedSearchRepository(db).list_for_candidate(candidate.id)
    return [SavedSearchRead.model_validate(r) for r in rows]


@router.post("/me/saved-searches", response_model=SavedSearchRead, status_code=201)
async def create_saved_search(
    data: SavedSearchCreate,
    candidate: CurrentCandidate,
    db: AsyncSession = Depends(get_db),
) -> SavedSearchRead:
    ss = await SavedSearchRepository(db).create(
        candidate.id, data.name, data.query, data.notify_email,
    )
    return SavedSearchRead.model_validate(ss)


@router.delete("/me/saved-searches/{search_id}", status_code=204)
async def delete_saved_search(
    search_id: uuid.UUID,
    candidate: CurrentCandidate,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await SavedSearchRepository(db).delete(candidate.id, search_id)
    return Response(status_code=204)


# ─────────────────────────────────────────────────────────────────────
# Search log — public endpoint, attribute to candidate if logged in
# ─────────────────────────────────────────────────────────────────────
@router.post("/search-log", status_code=204)
async def log_search(
    data: SearchLogCreate,
    candidate: OptionalCandidate,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await SearchLogRepository(db).log(
        candidate_id=candidate.id if candidate else None,
        query_text=data.query_text,
        category=data.category,
        location=data.location,
    )
    return Response(status_code=204)
