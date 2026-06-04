"""Company-side article CRUD.

Mounted at /company/articles (singular `/company` to match the existing
owner-self pattern of /api/v1/company/*). Every endpoint resolves
`CurrentCompany` from the recruiter session and scopes operations to
articles where company_id == current company.

Key invariants vs the admin router:
  • Always sets type='company' on create — companies can't smuggle a
    branded article into the editorial section.
  • Refuses to flip is_featured — the featured slot stays admin-curated.
  • Refuses to switch ownership to another company — once written, owned.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.modules.articles.models import Article
from app.modules.articles.schemas import (
    ArticleAdminList,
    ArticleAdminRead,
    ArticleCreate,
    ArticleUpdate,
)
from app.services.image_storage import ImageStorageService

router = APIRouter()
_cover_storage = ImageStorageService("article-covers")


# ─────────────────────────────────────────────────────────────────────
# List / get — scoped to current company
# ─────────────────────────────────────────────────────────────────────


@router.get("", response_model=ArticleAdminList)
async def list_company_articles(
    company: CurrentCompany,
    _user: CurrentUser,
    q: str | None = Query(None, min_length=1),
    status_filter: str | None = Query(None, alias="status", pattern="^(draft|published)$"),
    sort: str = Query("newest", pattern="^(newest|oldest|title)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    base = select(Article).where(Article.company_id == company.id, Article.type == "company")

    if q:
        term = f"%{q.strip()}%"
        base = base.where(Article.title.ilike(term) | Article.slug.ilike(term))
    if status_filter == "draft":
        base = base.where(Article.is_published.is_(False))
    elif status_filter == "published":
        base = base.where(Article.is_published.is_(True))

    if sort == "oldest":
        base = base.order_by(Article.created_at.asc())
    elif sort == "title":
        base = base.order_by(Article.title.asc())
    else:
        base = base.order_by(Article.created_at.desc())

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.offset(skip).limit(limit))).scalars().all()
    return {"items": [_owner_read(a) for a in rows], "total": total}


@router.get("/{article_id}", response_model=ArticleAdminRead)
async def get_company_article(
    article_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    article = await _require_owned(db, article_id, company.id)
    return _owner_read(article)


# ─────────────────────────────────────────────────────────────────────
# Create / update / delete
# ─────────────────────────────────────────────────────────────────────


@router.post("", response_model=ArticleAdminRead, status_code=status.HTTP_201_CREATED)
async def create_company_article(
    data: ArticleCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if data.is_featured:
        # Companies can't grab the featured slot. Admin-only.
        raise ForbiddenError("Tylko administrator może oznaczyć artykuł jako polecany.")
    if await _slug_taken(db, data.slug, exclude_id=None):
        raise ConflictError("Artykuł o tym adresie URL już istnieje.")

    published_at = data.published_at
    if data.is_published and not published_at:
        published_at = datetime.now(UTC)

    article = Article(
        slug=data.slug,
        title=data.title,
        excerpt=data.excerpt,
        content=data.content,
        category=data.category,
        is_featured=False,
        is_published=data.is_published,
        type="company",
        company_id=company.id,
        author_name=data.author_name,
        author_role=data.author_role,
        author_avatar_url=data.author_avatar_url,
        read_time_minutes=data.read_time_minutes,
        published_at=published_at,
    )
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return _owner_read(article)


@router.patch("/{article_id}", response_model=ArticleAdminRead)
async def update_company_article(
    article_id: uuid.UUID,
    data: ArticleUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    article = await _require_owned(db, article_id, company.id)

    payload = data.model_dump(exclude_unset=True)
    # Never let the owner promote themselves into the featured slot.
    payload.pop("is_featured", None)

    if (
        "slug" in payload
        and payload["slug"] != article.slug
        and await _slug_taken(db, payload["slug"], exclude_id=article.id)
    ):
        raise ConflictError("Artykuł o tym adresie URL już istnieje.")

    if (
        payload.get("is_published") is True
        and not article.published_at
        and "published_at" not in payload
    ):
        payload["published_at"] = datetime.now(UTC)

    for field, value in payload.items():
        setattr(article, field, value)
    await db.commit()
    await db.refresh(article)
    return _owner_read(article)


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company_article(
    article_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    article = await _require_owned(db, article_id, company.id)
    _cover_storage.delete(article.cover_image_url)
    await db.delete(article)
    await db.commit()
    return Response(status_code=204)


@router.post("/{article_id}/publish", response_model=ArticleAdminRead)
async def toggle_publish(
    article_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    article = await _require_owned(db, article_id, company.id)
    article.is_published = not article.is_published
    if article.is_published and not article.published_at:
        article.published_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(article)
    return _owner_read(article)


# ─────────────────────────────────────────────────────────────────────
# Cover upload
# ─────────────────────────────────────────────────────────────────────


@router.post("/{article_id}/cover", response_model=ArticleAdminRead)
async def upload_cover(
    article_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    article = await _require_owned(db, article_id, company.id)
    new_url = await _cover_storage.save(file)
    _cover_storage.delete(article.cover_image_url)
    article.cover_image_url = new_url
    await db.commit()
    await db.refresh(article)
    return _owner_read(article)


@router.delete("/{article_id}/cover", response_model=ArticleAdminRead)
async def remove_cover(
    article_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    article = await _require_owned(db, article_id, company.id)
    _cover_storage.delete(article.cover_image_url)
    article.cover_image_url = None
    await db.commit()
    await db.refresh(article)
    return _owner_read(article)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


async def _require_owned(db: AsyncSession, article_id: uuid.UUID, company_id: uuid.UUID) -> Article:
    result = await db.execute(
        select(Article).where(Article.id == article_id, Article.company_id == company_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        # 404 (not 403) — don't leak the existence of other companies' articles.
        raise NotFoundError("Artykuł nie został znaleziony.")
    return article


async def _slug_taken(db: AsyncSession, slug: str, exclude_id: uuid.UUID | None) -> bool:
    stmt = select(Article.id).where(Article.slug == slug)
    if exclude_id is not None:
        stmt = stmt.where(Article.id != exclude_id)
    return (await db.execute(stmt)).scalar_one_or_none() is not None


def _owner_read(a: Article) -> dict[str, Any]:
    company_block = (
        {
            "id": a.company.id,
            "slug": a.company.slug,
            "name": a.company.name,
            "logo_url": a.company.logo_url,
            "is_verified": a.company.is_verified,
        }
        if a.company
        else None
    )
    return {
        "id": a.id,
        "slug": a.slug,
        "title": a.title,
        "excerpt": a.excerpt,
        "cover_image_url": a.cover_image_url,
        "category": a.category,
        "is_featured": a.is_featured,
        "is_published": a.is_published,
        "type": a.type,
        "company": company_block,
        "author": {
            "name": a.author_name,
            "role": a.author_role,
            "avatar_url": a.author_avatar_url,
        },
        "read_time_minutes": a.read_time_minutes,
        "published_at": a.published_at,
        "content": a.content,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }
