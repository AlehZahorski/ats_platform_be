"""Data-consistency / model-hardening regression tests — Faza 2 (plan-naprawy).

Covers:
- review status enum aligned with the DB CHECK (no approved/rejected drift),
- candidate_scores one-per-(application, recruiter) invariant + partial-NULL
  semantics,
- notes.visible_to_candidate is reserved (no candidate read path leaks notes).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.enums.reviews import ReviewStatus
from app.core.security import create_access_token
from app.modules.applications.models import CandidateScore
from app.services.mailer import mail_service
from tests.helpers import (
    create_application,
    create_company,
    create_job,
    create_pipeline_stages,
    create_verified_user,
)


@pytest.fixture(autouse=True)
def _disable_email_sending(monkeypatch: pytest.MonkeyPatch) -> None:
    # The disposable test runner / CI may not ship the email Jinja templates;
    # these tests don't exercise mail, so stub the senders to no-ops.
    monkeypatch.setattr(mail_service, "send_application_confirmation", lambda *a, **k: None)
    monkeypatch.setattr(mail_service, "send_status_change", lambda *a, **k: None)
    monkeypatch.setattr(mail_service, "send_html", lambda *a, **k: None)


def _token(user_id: uuid.UUID, company_id: uuid.UUID) -> str:
    return create_access_token(str(user_id), {"company_id": str(company_id), "role": "owner"})


# ── reviews enum ↔ DB CHECK ──────────────────────────────────────────────────


def test_review_status_enum_matches_db_check() -> None:
    # Must equal the values allowed by ck_review_assignments_status. The old
    # approved/rejected members were never DB-valid and are now gone.
    assert {s.value for s in ReviewStatus} == {"pending", "submitted", "revoked"}


@pytest.mark.asyncio
async def test_review_status_db_check_allows_only_aligned_values(db_session) -> None:
    row = (
        await db_session.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_review_assignments_status'"
            )
        )
    ).scalar_one()
    assert "revoked" in row
    assert "approved" not in row
    assert "rejected" not in row


# ── candidate_scores uniqueness ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_candidate_scores_partial_unique_index_exists(db_session) -> None:
    exists = (
        await db_session.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE indexname = 'uq_candidate_scores_application_recruiter'"
            )
        )
    ).scalar_one_or_none()
    assert exists == 1


@pytest.mark.asyncio
async def test_candidate_scores_allows_multiple_null_recruiter(db_session) -> None:
    """Partial index (recruiter_id IS NOT NULL) must let orphaned NULL rows
    coexist — otherwise ON DELETE SET NULL would fail for two departed
    recruiters who scored the same application."""
    comp = await create_company(db_session, "Null Co")
    job = await create_job(db_session, comp.id, "Role", "open")
    app = await create_application(db_session, job.id, email="c@null.test")
    db_session.add_all(
        [
            CandidateScore(application_id=app.id, recruiter_id=None, communication=3),
            CandidateScore(application_id=app.id, recruiter_id=None, communication=4),
        ]
    )
    await db_session.flush()  # must NOT raise


@pytest.mark.asyncio
async def test_candidate_score_upsert_is_idempotent_per_recruiter(
    client: AsyncClient, db_session
) -> None:
    comp = await create_company(db_session, "Score Co")
    user = await create_verified_user(db_session, comp.id, "hr@score.test")
    await create_pipeline_stages(db_session)
    job = await create_job(db_session, comp.id, "Role", "open")
    await db_session.commit()

    client.cookies.clear()
    apply = await client.post(
        f"/api/v1/applications/apply/{job.id}",
        data={"first_name": "S", "last_name": "C", "email": "cand-score@example.com"},
    )
    app_id = apply.json()["id"]

    client.cookies.set("access_token", _token(user.id, comp.id))
    for value in (3, 5):  # score twice as the SAME recruiter
        resp = await client.post(
            f"/api/v1/applications/{app_id}/score",
            json={"communication": value, "technical": value, "culture_fit": value},
        )
        assert resp.status_code == 200

    count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM candidate_scores "
                "WHERE application_id = :aid AND recruiter_id = :rid"
            ),
            {"aid": app_id, "rid": str(user.id)},
        )
    ).scalar_one()
    assert count == 1  # re-scoring updated the row, did not duplicate


# ── notes are not candidate-visible ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_track_does_not_leak_notes(client: AsyncClient, db_session) -> None:
    comp = await create_company(db_session, "Track Co")
    user = await create_verified_user(db_session, comp.id, "hr@track.test")
    await create_pipeline_stages(db_session)
    job = await create_job(db_session, comp.id, "Role", "open")
    await db_session.commit()

    client.cookies.clear()
    apply = await client.post(
        f"/api/v1/applications/apply/{job.id}",
        data={"first_name": "T", "last_name": "C", "email": "cand-track@example.com"},
    )
    body = apply.json()
    app_id, token = body["id"], body["public_token"]

    # HR adds a note even flagged visible_to_candidate — there is still no
    # candidate read path, so it must never appear on the public tracking page.
    client.cookies.set("access_token", _token(user.id, comp.id))
    secret = "SECRET-INTERNAL-NOTE-9c1f"
    note = await client.post(
        f"/api/v1/notes/applications/{app_id}/notes",
        json={"content": secret, "visible_to_candidate": True},
    )
    assert note.status_code == 201

    client.cookies.clear()
    track = await client.get(f"/api/v1/applications/track/{token}")
    assert track.status_code == 200
    assert secret not in track.text
    assert "notes" not in track.json()
