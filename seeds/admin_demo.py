"""Bootstrap the first platform admin.

Creates a single admin row (admin@wakanta.pl) with a password from the
ADMIN_SEED_PASSWORD env var, falling back to 'admin1234' for local
dev. Idempotent — re-running just resets the password to whatever is
currently in the env (useful when you forget it).

Run inside the backend container:

    docker compose exec backend python seeds/admin_demo.py
    ADMIN_SEED_EMAIL=ja@wakanta.pl ADMIN_SEED_PASSWORD=tajne docker compose exec ...
"""
from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, ".")
from app.core.config import settings
from app.core.security import hash_password

# Need every model so cross-module relationships resolve at flush time.
import app.modules.admins.models  # noqa: F401
import app.modules.applications.models  # noqa: F401
import app.modules.articles.models  # noqa: F401
import app.modules.audit.models  # noqa: F401
import app.modules.automation.models  # noqa: F401
import app.modules.candidates.models  # noqa: F401
import app.modules.companies.models  # noqa: F401
import app.modules.consents.models  # noqa: F401
import app.modules.email_templates.models  # noqa: F401
import app.modules.forms.models  # noqa: F401
import app.modules.interviews.models  # noqa: F401
import app.modules.jobs.analysis_models  # noqa: F401
import app.modules.jobs.models  # noqa: F401
import app.modules.notes.models  # noqa: F401
import app.modules.organizer.models  # noqa: F401
import app.modules.pipeline.models  # noqa: F401
import app.modules.reviews.models  # noqa: F401
import app.modules.tags.models  # noqa: F401
import app.modules.tasks.models  # noqa: F401
import app.modules.users.models  # noqa: F401

from app.modules.admins.models import Admin


async def main() -> None:
    email = os.environ.get("ADMIN_SEED_EMAIL", "admin@wakanta.pl").strip().lower()
    password = os.environ.get("ADMIN_SEED_PASSWORD", "admin1234")
    full_name = os.environ.get("ADMIN_SEED_NAME", "Platform Admin")

    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        existing = (await db.execute(select(Admin).where(Admin.email == email))).scalar_one_or_none()
        if existing:
            # Re-running rotates the password — handy if dev forgets it.
            existing.password_hash = hash_password(password)
            existing.full_name = full_name
            existing.is_active = True
            await db.commit()
            print(f"✓ Reset password for existing admin: {email}")
        else:
            admin = Admin(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                is_active=True,
            )
            db.add(admin)
            await db.commit()
            print(f"✓ Created admin: {email}")

    print(f"  → login at /admin/login with password: {password}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
