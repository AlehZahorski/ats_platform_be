"""Demo companies for the public /firmy listing + profile pages.

Creates ~8 curated companies in the style of the wakanta.pl Firmy mockup
(Ramp, Brainly, Infermedica, Docplanner, CD Projekt Red, Revolut, Tidio,
Vue Storefront). Each has a different completeness level so the
"hide empty sections" rendering on /firmy/{slug} can be verified end-to-end:

  • 4 "full"     — every section filled (timeline, FAQ, benefits, …)
  • 2 "partial"  — half the sections empty
  • 2 "minimal"  — name, industry, location, employee_count only

For each company we also drop 3–5 open jobs so the profile's
"Aktualne oferty pracy" section has real content. Job descriptions
intentionally lightweight — public job board has its own dedicated
seed (job_board_seed.py) for volume testing.

Run inside the backend container:

    docker compose exec backend python seeds/companies_demo.py
    docker compose exec backend python seeds/companies_demo.py --reset

Idempotent: every seeded row is tagged "(demo)" in the name so --reset
deletes only seed rows and leaves real companies alone.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, ".")
from app.core.config import settings
from app.core.security import hash_password

# Import every model module so SQLAlchemy can resolve cross-module
# relationships at flush time (otherwise lazy resolution of "Application",
# "FormTemplate" etc. fails).
import app.modules.applications.models  # noqa: F401
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

from app.modules.companies.models import Company
from app.modules.jobs.models import Job
from app.modules.users.models import User


SEED_TAG = "(demo)"


# ──────────────────────────────────────────────────────────────────────
# Reusable section snippets
# ──────────────────────────────────────────────────────────────────────

HOW_WE_WORK_REMOTE_FIRST = [
    {"icon": "globe",        "title": "Remote-first",          "description": "Pracujemy z dowolnego miejsca na świecie."},
    {"icon": "calendar-off", "title": "No-meetings Wednesdays","description": "Środa bez spotkań to świętość."},
    {"icon": "messages",     "title": "Async-first",           "description": "Komunikacja asynchroniczna to nasz standard."},
    {"icon": "compass",      "title": "Ownership",             "description": "Masz wpływ na produkt i decyzje."},
    {"icon": "rocket",       "title": "Ship fast",             "description": "Małe zespoły, szybkie decyzje."},
]

HOW_WE_WORK_HYBRID = [
    {"icon": "building",     "title": "Hybryda 2+3",            "description": "Dwa dni w biurze, trzy zdalnie."},
    {"icon": "users",        "title": "Małe zespoły",           "description": "Maks. 8 osób na squad — nikt się nie gubi."},
    {"icon": "graduation-cap","title": "Czas na naukę",         "description": "10% czasu pracy na rozwój własny."},
    {"icon": "heart",        "title": "Psychological safety",   "description": "Pytania głupie nie istnieją."},
]

BENEFITS_STANDARD = [
    "Elastyczne godziny pracy",
    "Budżet szkoleniowy 5 000 PLN / rok",
    "Sprzęt najwyższej jakości (MacBook Pro)",
    "Opieka medyczna premium (Luxmed)",
    "Budżet wellbeing 500 PLN / miesiąc",
    "20 dni płatnego urlopu + sick days",
    "Karta Multisport",
]

BENEFITS_PARTIAL = [
    "Prywatna opieka medyczna",
    "Karta sportowa",
    "Elastyczne godziny pracy",
]

RECRUITMENT_PROCESS_STANDARD = [
    {"name": "Rozmowa wstępna",       "duration": "15 min"},
    {"name": "Rozmowa techniczna",    "duration": "60 min"},
    {"name": "Case study (na żywo)",  "duration": None},
    {"name": "Rozmowa z zespołem",    "duration": None},
    {"name": "Oferta",                "duration": None},
]

FAQ_STANDARD = [
    {"question": "Czy oferujecie pracę w pełni zdalną?",  "answer": "Tak — wszystkie role inżynierskie i produktowe są w pełni remote-friendly. Współpracujemy z osobami z całej UE."},
    {"question": "Jak wygląda onboarding?",                "answer": "Pierwszy tydzień to integracja z zespołem i poznanie produktu. Każdy nowy pracownik dostaje buddy'ego, który prowadzi go przez pierwszy miesiąc."},
    {"question": "Jakie są możliwości rozwoju?",           "answer": "Coroczne IDP, budżet szkoleniowy, ścieżki kariery zarówno IC, jak i management. Konferencje opłacane przez firmę."},
    {"question": "Jak wygląda typowy dzień pracy?",        "answer": "Krótkie standup'y rano (15 min), bloki focus time po południu. Środy bez spotkań. Komunikacja głównie async."},
]


# ──────────────────────────────────────────────────────────────────────
# Demo companies
# ──────────────────────────────────────────────────────────────────────

def _full_profile(name: str, industry: str, hq: str, employees: int, founded: int, remote_pct: int,
                  tech: list[str], timeline: list[dict[str, Any]], how_we_work: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name":               f"{name} {SEED_TAG}",
        "slug":               name.lower().replace(" ", "-"),
        "is_verified":        True,
        "tagline":            "Nowoczesna platforma — zbudowana z myślą o przyszłości.",
        "description":        f"{name} to firma działająca w sektorze {industry.lower()}, której misją jest dostarczanie najlepszych rozwiązań klientom z całej Europy.",
        "industry":           industry,
        "employee_count":     employees,
        "hq_location":        hq,
        "founded_year":       founded,
        "website":            f"https://{name.lower().replace(' ', '')}.example.com",
        "remote_percentage":  remote_pct,
        "tech_stack":         tech,
        "how_we_work":        how_we_work,
        "benefits":           BENEFITS_STANDARD,
        "recruitment_process": RECRUITMENT_PROCESS_STANDARD,
        "timeline":           timeline,
        "faq":                FAQ_STANDARD,
        "gallery":            [],  # uploads handled in etap 2
    }


def _partial_profile(name: str, industry: str, hq: str, employees: int, founded: int, remote_pct: int,
                     tech: list[str]) -> dict[str, Any]:
    """Half-filled profile — exercise the 'hide empty sections' renderer."""
    return {
        "name":               f"{name} {SEED_TAG}",
        "slug":               name.lower().replace(" ", "-"),
        "is_verified":        True,
        "tagline":            "Tworzymy świetne produkty z pasją.",
        "description":        f"{name} działa w sektorze {industry.lower()} od {2026 - founded} lat.",
        "industry":           industry,
        "employee_count":     employees,
        "hq_location":        hq,
        "founded_year":       founded,
        "website":            None,
        "remote_percentage":  remote_pct,
        "tech_stack":         tech,
        "how_we_work":        [],   # ← empty: section hidden
        "benefits":           BENEFITS_PARTIAL,
        "recruitment_process": [],  # ← empty: section hidden
        "timeline":           [],   # ← empty: section hidden
        "faq":                [],   # ← empty: section hidden
        "gallery":            [],
    }


def _minimal_profile(name: str, industry: str, hq: str, employees: int) -> dict[str, Any]:
    """Bare profile — only hero/KPI/jobs render, everything else hidden."""
    return {
        "name":               f"{name} {SEED_TAG}",
        "slug":               name.lower().replace(" ", "-"),
        "is_verified":        random.random() < 0.5,
        "tagline":            None,
        "description":        None,
        "industry":           industry,
        "employee_count":     employees,
        "hq_location":        hq,
        "founded_year":       None,
        "website":            None,
        "remote_percentage":  None,
        "tech_stack":         [],
        "how_we_work":        [],
        "benefits":           [],
        "recruitment_process": [],
        "timeline":           [],
        "faq":                [],
        "gallery":            [],
    }


def build_demo_companies() -> list[dict[str, Any]]:
    return [
        # ── Full (4) ─────────────────────────────────────────────────
        _full_profile(
            name="Ramp", industry="Fintech", hq="Nowy Jork, USA / Europa",
            employees=120, founded=2019, remote_pct=85,
            tech=["TypeScript", "React", "Go", "Python", "AWS", "Kubernetes",
                  "PostgreSQL", "Redis", "Docker", "Terraform", "Kafka", "Stripe"],
            timeline=[
                {"year": 2019, "title": "Założenie Ramp w Nowym Jorku"},
                {"year": 2020, "title": "Pierwsi klienci i produkt MVP"},
                {"year": 2021, "title": "Runda Seed 10M USD"},
                {"year": 2023, "title": "Runda Series A 50M USD"},
                {"year": 2024, "title": "Przekroczyliśmy 1M użytkowników"},
                {"year": 2025, "title": "Ekspansja do Europy"},
            ],
            how_we_work=HOW_WE_WORK_REMOTE_FIRST,
        ),
        _full_profile(
            name="Brainly", industry="EdTech", hq="Kraków, Polska",
            employees=250, founded=2009, remote_pct=60,
            tech=["React", "Scala", "Kotlin", "Python", "AWS", "GraphQL"],
            timeline=[
                {"year": 2009, "title": "Start jako Zadane.pl"},
                {"year": 2015, "title": "Ekspansja na USA"},
                {"year": 2020, "title": "100M użytkowników miesięcznie"},
            ],
            how_we_work=HOW_WE_WORK_HYBRID,
        ),
        _full_profile(
            name="Infermedica", industry="Healthtech", hq="Wrocław, Polska",
            employees=110, founded=2012, remote_pct=100,
            tech=["Python", "FastAPI", "PostgreSQL", "AWS", "Kubernetes"],
            timeline=[
                {"year": 2012, "title": "Powstanie firmy"},
                {"year": 2018, "title": "Pierwszy duży partner medyczny"},
                {"year": 2023, "title": "Series B"},
            ],
            how_we_work=HOW_WE_WORK_REMOTE_FIRST,
        ),
        _full_profile(
            name="Docplanner", industry="Healthtech", hq="Warszawa, Polska",
            employees=320, founded=2012, remote_pct=70,
            tech=["React", "Node.js", "MongoDB", "AWS", "TypeScript", "PHP"],
            timeline=[
                {"year": 2012, "title": "Start ZnanyLekarz.pl"},
                {"year": 2017, "title": "Akwizycja Doctoralia"},
                {"year": 2022, "title": "Obecność w 15 krajach"},
            ],
            how_we_work=HOW_WE_WORK_HYBRID,
        ),
        # ── Partial (2) ──────────────────────────────────────────────
        _partial_profile(
            name="CD Projekt Red", industry="Gaming", hq="Warszawa, Polska",
            employees=1100, founded=2002, remote_pct=20,
            tech=["C++", "REDengine", "Python"],
        ),
        _partial_profile(
            name="Revolut", industry="Fintech", hq="Londyn, UK / Zdalnie",
            employees=5000, founded=2015, remote_pct=60,
            tech=["Kotlin", "Go", "AWS", "Kafka"],
        ),
        # ── Minimal (2) ──────────────────────────────────────────────
        _minimal_profile(name="Tidio",         industry="SaaS",       hq="Gdańsk, Polska",  employees=160),
        _minimal_profile(name="Vue Storefront",industry="E-commerce", hq="Wrocław, Polska", employees=70),
    ]


# ──────────────────────────────────────────────────────────────────────
# Job stubs per company
# ──────────────────────────────────────────────────────────────────────

DEMO_JOB_TITLES = {
    "Fintech":     ["Senior Backend Engineer", "Product Designer", "DevOps Engineer", "Frontend Developer (React)"],
    "EdTech":      ["Mobile Engineer (Android)", "Data Scientist", "Engineering Manager"],
    "Healthtech":  ["Senior Python Engineer", "ML Engineer", "Clinical Content Lead", "Product Manager"],
    "Gaming":      ["Senior C++ Engineer", "Technical Artist", "Game Designer"],
    "SaaS":        ["Full-stack Engineer", "Customer Success Manager", "Growth Marketer"],
    "E-commerce":  ["Vue.js Developer", "Solution Architect", "Partner Manager"],
}

def make_demo_jobs(company: Company) -> list[Job]:
    titles = DEMO_JOB_TITLES.get(company.industry or "", ["Software Engineer", "Product Manager"])
    out: list[Job] = []
    for title in titles[: random.randint(3, len(titles))]:
        smin = random.choice([14_000, 16_000, 18_000, 20_000, 22_000])
        smax = smin + random.choice([6_000, 8_000, 10_000, 12_000])
        out.append(Job(
            company_id=company.id,
            title=f"{title} {SEED_TAG}",
            slug=f"{title.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
            location=company.hq_location or "Zdalnie",
            status="open",
            category="it_backend" if "Engineer" in title or "Developer" in title else "design_product",
            work_mode="remote" if (company.remote_percentage or 0) >= 80 else "hybrid",
            contract_type=random.choice(["employment", "b2b"]),
            seniority=random.choice(["junior", "mid", "senior"]),
            employment_size="full",
            role_summary=f"Dołącz do zespołu {company.name.replace(SEED_TAG, '').strip()} i rozwijaj produkt używany przez tysiące klientów.",
            tech_stack=", ".join(company.tech_stack[:6]) if company.tech_stack else None,
            salary_min=smin,
            salary_max=smax,
            salary_currency="PLN",
            salary_period="month",
        ))
    # Stagger created_at so "newest" sort produces meaningful output
    for j in out:
        j.created_at = datetime.now(UTC) - timedelta(days=random.randint(0, 14))
    return out


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

async def main(reset: bool = False) -> None:
    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        if reset:
            print(f"⚠ Wiping companies/jobs tagged '{SEED_TAG}'…")
            await db.execute(text(f"DELETE FROM jobs WHERE title LIKE '%{SEED_TAG}%'"))
            await db.execute(text(f"DELETE FROM users WHERE company_id IN (SELECT id FROM companies WHERE name LIKE '%{SEED_TAG}%')"))
            await db.execute(text(f"DELETE FROM companies WHERE name LIKE '%{SEED_TAG}%'"))
            await db.commit()

        password_hash = hash_password("password123")
        created = 0
        for profile in build_demo_companies():
            # Skip if already exists (idempotent re-runs without --reset)
            existing = (await db.execute(select(Company).where(Company.slug == profile["slug"]))).scalar_one_or_none()
            if existing:
                print(f"  · {profile['name']} — already present, skipping")
                continue

            company = Company(**profile)
            db.add(company)
            await db.flush()  # need company.id for owner + jobs

            db.add(User(
                company_id=company.id,
                email=f"owner-{company.id}@demo.local",
                password_hash=password_hash,
                role="owner",
                is_verified=True,
                language="pl",
            ))

            for job in make_demo_jobs(company):
                db.add(job)

            created += 1
            print(f"  ✓ {profile['name']}")

        await db.commit()
        print(f"Done — {created} demo companies created.")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Delete existing demo rows before seeding.")
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset))
