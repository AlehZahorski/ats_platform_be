"""Admin CRUD for Poradnik articles.

Sits behind CurrentAdmin so only platform admins can read drafts,
create new posts, upload covers, and toggle publish/featured flags.

URL prefix is `/admin/articles` (mounted from api/router.py), keeping
admin and public routes cleanly separated.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ConflictError, NotFoundError
from app.modules.admins.dependencies import CurrentAdmin
from app.modules.articles.models import Article
from app.modules.articles.schemas import (
    ArticleAdminList,
    ArticleAdminRead,
    ArticleCreate,
    ArticleUpdate,
)
from app.services.image_storage import ImageStorageService

router = APIRouter()

# Dedicated subdir so article covers don't mix with company assets.
_cover_storage = ImageStorageService("article-covers")


# ─────────────────────────────────────────────────────────────────────
# List / read
# ─────────────────────────────────────────────────────────────────────


@router.get("", response_model=ArticleAdminList)
async def admin_list_articles(
    _admin: CurrentAdmin,
    q: str | None = Query(None, min_length=1),
    category: str | None = Query(None),
    type: str | None = Query(None, pattern="^(editorial|company)$"),
    status_filter: str | None = Query(None, alias="status", pattern="^(draft|published)$"),
    sort: str = Query("newest", pattern="^(newest|oldest|title)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    base = select(Article)

    if q:
        term = f"%{q.strip()}%"
        base = base.where(Article.title.ilike(term) | Article.slug.ilike(term))
    if category:
        base = base.where(Article.category == category)
    if type:
        base = base.where(Article.type == type)
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
    return {"items": [_admin_read(a) for a in rows], "total": total}


@router.get("/{article_id}", response_model=ArticleAdminRead)
async def admin_get_article(
    article_id: uuid.UUID,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    article = await _require(db, article_id)
    return _admin_read(article)


# ─────────────────────────────────────────────────────────────────────
# Create / update / delete
# ─────────────────────────────────────────────────────────────────────


@router.post("", response_model=ArticleAdminRead, status_code=status.HTTP_201_CREATED)
async def admin_create_article(
    data: ArticleCreate,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if await _slug_taken(db, data.slug, exclude_id=None):
        raise ConflictError("Artykuł o tym adresie URL już istnieje.")
    # Auto-stamp published_at when publishing without an explicit date.
    published_at = data.published_at
    if data.is_published and not published_at:
        published_at = datetime.now(timezone.utc)

    article = Article(
        slug=data.slug,
        title=data.title,
        excerpt=data.excerpt,
        content=data.content,
        category=data.category,
        is_featured=data.is_featured,
        is_published=data.is_published,
        author_name=data.author_name,
        author_role=data.author_role,
        author_avatar_url=data.author_avatar_url,
        read_time_minutes=data.read_time_minutes,
        published_at=published_at,
    )
    db.add(article)
    await db.flush()
    # Featured invariant: only one at a time.
    if article.is_featured:
        await _unfeature_others(db, keep_id=article.id)
    await db.commit()
    await db.refresh(article)
    return _admin_read(article)


@router.patch("/{article_id}", response_model=ArticleAdminRead)
async def admin_update_article(
    article_id: uuid.UUID,
    data: ArticleUpdate,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    article = await _require(db, article_id)
    payload = data.model_dump(exclude_unset=True)

    if "slug" in payload and payload["slug"] != article.slug:
        if await _slug_taken(db, payload["slug"], exclude_id=article.id):
            raise ConflictError("Artykuł o tym adresie URL już istnieje.")

    # When flipping is_published true the first time, stamp published_at
    # for the editor's convenience (they don't have to set it manually).
    if (
        payload.get("is_published") is True
        and not article.published_at
        and "published_at" not in payload
    ):
        payload["published_at"] = datetime.now(timezone.utc)

    for field, value in payload.items():
        setattr(article, field, value)
    await db.flush()

    if article.is_featured:
        await _unfeature_others(db, keep_id=article.id)
    await db.commit()
    await db.refresh(article)
    return _admin_read(article)


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_article(
    article_id: uuid.UUID,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
) -> Response:
    article = await _require(db, article_id)
    # Best-effort cover cleanup so we don't accumulate orphan files on disk.
    _cover_storage.delete(article.cover_image_url)
    await db.delete(article)
    await db.commit()
    return Response(status_code=204)


# ─────────────────────────────────────────────────────────────────────
# Quick toggles — used by the list view to flip flags without
# round-tripping through the full edit form.
# ─────────────────────────────────────────────────────────────────────


@router.post("/{article_id}/publish", response_model=ArticleAdminRead)
async def admin_toggle_publish(
    article_id: uuid.UUID,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    article = await _require(db, article_id)
    article.is_published = not article.is_published
    if article.is_published and not article.published_at:
        article.published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(article)
    return _admin_read(article)


@router.post("/{article_id}/feature", response_model=ArticleAdminRead)
async def admin_toggle_feature(
    article_id: uuid.UUID,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    article = await _require(db, article_id)
    article.is_featured = not article.is_featured
    await db.flush()
    if article.is_featured:
        await _unfeature_others(db, keep_id=article.id)
    await db.commit()
    await db.refresh(article)
    return _admin_read(article)


# ─────────────────────────────────────────────────────────────────────
# Promotion — lifts a company article into the editorial /poradnik feed
# for a defined window. `days` = null means "remove promotion".
# ─────────────────────────────────────────────────────────────────────

from datetime import UTC, timedelta  # noqa: E402  — kept local to keep top imports tidy


@router.post("/{article_id}/promote", response_model=ArticleAdminRead)
async def admin_promote_article(
    article_id: uuid.UUID,
    _admin: CurrentAdmin,
    days: int | None = Query(
        None, ge=1, le=365, description="Window length in days. Omit to unpromote."
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    article = await _require(db, article_id)
    if article.type != "company":
        # Promotion only makes sense for brand content — editorial articles
        # already live on /poradnik by default.
        raise NotFoundError("Promocja dotyczy tylko artykułów firmowych.")
    if days is None:
        article.is_promoted = False
        article.promoted_until = None
    else:
        article.is_promoted = True
        article.promoted_until = datetime.now(UTC) + timedelta(days=days)
    await db.commit()
    await db.refresh(article)
    return _admin_read(article)


# ─────────────────────────────────────────────────────────────────────
# Cover upload — separate endpoint, swaps the URL and cleans up the
# previous file. Returns the refreshed admin view so the editor can
# update its preview without an extra GET.
# ─────────────────────────────────────────────────────────────────────


@router.post("/{article_id}/cover", response_model=ArticleAdminRead)
async def admin_upload_cover(
    article_id: uuid.UUID,
    _admin: CurrentAdmin,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    article = await _require(db, article_id)
    new_url = await _cover_storage.save(file)
    _cover_storage.delete(article.cover_image_url)
    article.cover_image_url = new_url
    await db.commit()
    await db.refresh(article)
    return _admin_read(article)


@router.delete("/{article_id}/cover", response_model=ArticleAdminRead)
async def admin_remove_cover(
    article_id: uuid.UUID,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    article = await _require(db, article_id)
    _cover_storage.delete(article.cover_image_url)
    article.cover_image_url = None
    await db.commit()
    await db.refresh(article)
    return _admin_read(article)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


async def _require(db: AsyncSession, article_id: uuid.UUID) -> Article:
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        raise NotFoundError("Artykuł nie został znaleziony.")
    return article


async def _slug_taken(db: AsyncSession, slug: str, exclude_id: uuid.UUID | None) -> bool:
    stmt = select(Article.id).where(Article.slug == slug)
    if exclude_id is not None:
        stmt = stmt.where(Article.id != exclude_id)
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def _unfeature_others(db: AsyncSession, keep_id: uuid.UUID) -> None:
    """Featured slot is exclusive — only one article carries the badge.
    Whenever we mark a new one, the previous featured loses the flag."""
    await db.execute(
        update(Article)
        .where(Article.id != keep_id, Article.is_featured.is_(True))
        .values(is_featured=False)
    )


def _admin_read(a: Article) -> dict[str, Any]:
    # Brand-company block — only emitted for type='company' rows, same
    # shape as the public side so the FE can render moderation views
    # without a second fetch.
    company_block: dict[str, Any] | None = None
    if a.type == "company" and a.company:
        company_block = {
            "id": a.company.id,
            "slug": a.company.slug,
            "name": a.company.name,
            "logo_url": a.company.logo_url,
            "is_verified": a.company.is_verified,
        }
    return {
        "id": a.id,
        "slug": a.slug,
        "title": a.title,
        "excerpt": a.excerpt,
        "cover_image_url": a.cover_image_url,
        "category": a.category,
        "is_featured": a.is_featured,
        "is_published": a.is_published,
        "is_promoted": a.is_promoted,
        "promoted_until": a.promoted_until,
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
