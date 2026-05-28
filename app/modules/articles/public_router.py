"""Public Poradnik endpoints. No auth — content is meant to be read.

Mirrors the company public router pattern: separate file so the route
prefix can stay plural (`/articles`) while any future authenticated
admin endpoints live in their own router.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.modules.articles.models import Article, NewsletterSubscriber
from app.modules.articles.schemas import (
    ArticleAuthor,
    ArticleDetail,
    ArticleList,
    ArticleSummary,
    CategoryCount,
    NewsletterSubscribeRequest,
    NewsletterSubscribeResponse,
)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Articles — list / featured / categories / detail
# ─────────────────────────────────────────────────────────────────────

@router.get("/public", response_model=ArticleList)
async def list_public_articles(
    q:        str | None = Query(None, min_length=1),
    category: str | None = Query(None),
    type:     str        = Query("editorial", pattern="^(editorial|company|all)$", description="Filter by article flavour."),
    sort:     str        = Query("newest", pattern="^(newest|oldest)$"),
    skip:     int        = Query(0, ge=0),
    limit:    int        = Query(12, ge=1, le=60),
    exclude_featured: bool = Query(False, description="Skip articles flagged as featured — used by the grid below the hero card."),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    base = select(Article).where(Article.is_published.is_(True))

    # /poradnik view (type=editorial) also surfaces actively-promoted
    # company articles — that's how brand content earns its slot. The
    # /firmy-pisza view (type=company) shows ALL published company posts
    # regardless of promotion (the brand section is their home).
    now = datetime.now(timezone.utc)
    if type == "editorial":
        base = base.where(
            or_(
                Article.type == "editorial",
                and_(
                    Article.type == "company",
                    Article.is_promoted.is_(True),
                    or_(Article.promoted_until.is_(None), Article.promoted_until > now),
                ),
            )
        )
    elif type == "company":
        base = base.where(Article.type == "company")
    # type == "all" — no extra filter

    if q:
        term = f"%{q.strip()}%"
        base = base.where(Article.title.ilike(term) | Article.excerpt.ilike(term))
    if category:
        base = base.where(Article.category == category)
    if exclude_featured:
        base = base.where(Article.is_featured.is_(False))

    if sort == "oldest":
        base = base.order_by(Article.published_at.asc().nullslast(), Article.created_at.asc())
    else:
        base = base.order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.offset(skip).limit(limit))).scalars().all()

    return {"items": [_summary(a) for a in rows], "total": total}


@router.get("/public/featured", response_model=ArticleSummary | None)
async def get_featured_article(
    type: str = Query("editorial", pattern="^(editorial|company|all)$"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any] | None:
    """Picks the most recently published article flagged is_featured.
    Defaults to editorial — company articles can also be featured, but
    only admin toggles that flag so the slot stays curated."""
    stmt = select(Article).where(Article.is_published.is_(True), Article.is_featured.is_(True))
    if type != "all":
        stmt = stmt.where(Article.type == type)
    result = await db.execute(
        stmt.order_by(Article.published_at.desc().nullslast(), Article.created_at.desc()).limit(1)
    )
    article = result.scalar_one_or_none()
    return _summary(article) if article else None


@router.get("/public/categories", response_model=list[CategoryCount])
async def list_categories(
    type: str = Query("editorial", pattern="^(editorial|company|all)$"),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Counts published articles per category. Drives the chip row at
    the top of /poradnik and /firmy-pisza. For 'editorial' we include
    actively-promoted company articles so the chip counts match what the
    user actually sees in the grid below."""
    stmt = (
        select(Article.category, func.count(Article.id).label("count"))
        .where(Article.is_published.is_(True))
    )

    now = datetime.now(timezone.utc)
    if type == "editorial":
        stmt = stmt.where(
            or_(
                Article.type == "editorial",
                and_(
                    Article.type == "company",
                    Article.is_promoted.is_(True),
                    or_(Article.promoted_until.is_(None), Article.promoted_until > now),
                ),
            )
        )
    elif type == "company":
        stmt = stmt.where(Article.type == "company")

    rows = (await db.execute(
        stmt.group_by(Article.category).order_by(func.count(Article.id).desc())
    )).all()
    return [{"category": row.category, "count": row.count} for row in rows]


@router.get("/public/{slug}", response_model=ArticleDetail)
async def get_public_article(slug: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    article = (await db.execute(
        select(Article).where(Article.slug == slug, Article.is_published.is_(True))
    )).scalar_one_or_none()
    if not article:
        raise NotFoundError("Artykuł nie został znaleziony.")
    return _detail(article)


# ─────────────────────────────────────────────────────────────────────
# Newsletter — collect an email, no sending pipeline yet.
# ─────────────────────────────────────────────────────────────────────

@router.post("/newsletter/subscribe", response_model=NewsletterSubscribeResponse, status_code=201)
async def newsletter_subscribe(
    data: NewsletterSubscribeRequest,
    db: AsyncSession = Depends(get_db),
) -> NewsletterSubscribeResponse:
    email_norm = data.email.strip().lower()

    existing = (await db.execute(
        select(NewsletterSubscriber).where(NewsletterSubscriber.email == email_norm)
    )).scalar_one_or_none()

    if existing:
        # Idempotent re-subscribe: bump the timestamp + clear any prior
        # unsubscribe so the user lands back on the list, then return.
        existing.subscribed_at = datetime.now(timezone.utc)
        existing.unsubscribed_at = None
        if data.source and not existing.source:
            existing.source = data.source
        await db.flush()
        await db.refresh(existing)
        return NewsletterSubscribeResponse(
            email=existing.email,
            subscribed_at=existing.subscribed_at,
            already_existed=True,
        )

    sub = NewsletterSubscriber(
        email=email_norm,
        source=data.source,
        subscribed_at=datetime.now(timezone.utc),
    )
    db.add(sub)
    await db.flush()
    await db.refresh(sub)
    return NewsletterSubscribeResponse(
        email=sub.email,
        subscribed_at=sub.subscribed_at,
        already_existed=False,
    )


# ─────────────────────────────────────────────────────────────────────
# Response shaping
# ─────────────────────────────────────────────────────────────────────

def _author(a: Article) -> ArticleAuthor:
    return ArticleAuthor(name=a.author_name, role=a.author_role, avatar_url=a.author_avatar_url)


def _brand_company(a: Article) -> dict[str, Any] | None:
    """Slim company block — only emitted for type='company' rows so
    /poradnik responses don't carry irrelevant data. FE branches on it
    to render either the editorial byline or the brand byline."""
    if a.type != "company" or not a.company:
        return None
    c = a.company
    return {
        "id":          c.id,
        "slug":        c.slug,
        "name":        c.name,
        "logo_url":    c.logo_url,
        "is_verified": c.is_verified,
    }


def _summary(a: Article) -> dict[str, Any]:
    return {
        "id": a.id,
        "slug": a.slug,
        "title": a.title,
        "excerpt": a.excerpt,
        "cover_image_url": a.cover_image_url,
        "category": a.category,
        "is_featured": a.is_featured,
        "is_promoted": a.is_promoted,
        "promoted_until": a.promoted_until,
        "type": a.type,
        "company": _brand_company(a),
        "author": _author(a),
        "read_time_minutes": a.read_time_minutes,
        "published_at": a.published_at,
    }


def _detail(a: Article) -> dict[str, Any]:
    return {**_summary(a), "content": a.content}
