import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.consents.schemas import (
    AnonymizeResult,
    ApplicationConsentCreate,
    ApplicationConsentRead,
    ConsentCreate,
    ConsentRead,
    ConsentUpdate,
    DataRetentionUpdate,
)
from app.modules.consents.service import ConsentService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> ConsentService:
    return ConsentService(db)


# ── Consent definitions ────────────────────────────────────────────────────────
@router.post("", response_model=ConsentRead, status_code=201)
async def create_consent(
    data: ConsentCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: ConsentService = Depends(_svc),
) -> ConsentRead:
    consent = await svc.create(company.id, data)
    return ConsentRead.model_validate(consent)


@router.get("", response_model=list[ConsentRead])
async def list_consents(
    company: CurrentCompany,
    _user: CurrentUser,
    active_only: bool = Query(False),
    language: Optional[str] = Query(None),
    svc: ConsentService = Depends(_svc),
) -> list[ConsentRead]:
    consents = await svc.list(company.id, active_only=active_only, language=language)
    return [ConsentRead.model_validate(c) for c in consents]


@router.patch("/{consent_id}", response_model=ConsentRead)
async def update_consent(
    consent_id: uuid.UUID,
    data: ConsentUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: ConsentService = Depends(_svc),
) -> ConsentRead:
    consent = await svc.update(consent_id, company.id, data)
    return ConsentRead.model_validate(consent)


@router.delete("/{consent_id}")
async def delete_consent(
    consent_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: ConsentService = Depends(_svc),
) -> Response:
    await svc.delete(consent_id, company.id)
    return Response(status_code=204)


# ── Application consents ───────────────────────────────────────────────────────
@router.post("/applications/{application_id}/consents", status_code=201)
async def record_consent(
    application_id: uuid.UUID,
    data: ApplicationConsentCreate,
    _company: CurrentCompany,
    _user: CurrentUser,
    svc: ConsentService = Depends(_svc),
) -> dict:
    await svc.record_application_consent(application_id, data)
    return {"recorded": True}


@router.get(
    "/applications/{application_id}/consents",
    response_model=list[ApplicationConsentRead],
)
async def get_application_consents(
    application_id: uuid.UUID,
    _company: CurrentCompany,
    _user: CurrentUser,
    svc: ConsentService = Depends(_svc),
) -> list[ApplicationConsentRead]:
    records = await svc.get_application_consents(application_id)
    return [ApplicationConsentRead.model_validate(r) for r in records]


# ── GDPR: data retention ───────────────────────────────────────────────────────
@router.patch("/applications/{application_id}/retention")
async def set_retention(
    application_id: uuid.UUID,
    data: DataRetentionUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: ConsentService = Depends(_svc),
) -> dict:
    await svc.set_retention(application_id, company.id, data)
    return {"updated": True}


# ── GDPR: anonymize ────────────────────────────────────────────────────────────
@router.post(
    "/applications/{application_id}/anonymize",
    response_model=AnonymizeResult,
)
async def anonymize_application(
    application_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: ConsentService = Depends(_svc),
) -> AnonymizeResult:
    return await svc.anonymize(application_id, company.id)


# ── GDPR: hard delete ──────────────────────────────────────────────────────────
@router.delete("/applications/{application_id}/data")
async def delete_application_data(
    application_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: ConsentService = Depends(_svc),
) -> dict:
    return await svc.delete_application_data(application_id, company.id)


# ── GDPR: cleanup expired ──────────────────────────────────────────────────────
@router.post("/cleanup")
async def cleanup_expired(
    company: CurrentCompany,
    _user: CurrentUser,
    svc: ConsentService = Depends(_svc),
) -> dict:
    return await svc.cleanup_expired(company.id)