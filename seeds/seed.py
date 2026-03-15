"""
Database Seeder for ATS Platform
=================================
Run from the backend/ directory with venv active:

    python seeds/seed.py

Options:
    python seeds/seed.py --fresh     # Drop all data first, then seed
    python seeds/seed.py --stages    # Seed only pipeline stages (safe to run anytime)
"""

import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── bootstrap path so we can import app modules ──────────────────────────────
sys.path.insert(0, ".")
from app.core.config import settings
from app.core.security import generate_public_token, hash_password

# ── models ───────────────────────────────────────────────────────────────────
from app.modules.applications.models import Application, ApplicationAnswer, CandidateScore
from app.modules.audit.models import AuditLog
from app.modules.companies.models import Company
from app.modules.forms.models import FormField, FormTemplate
from app.modules.jobs.models import Job, JobFormTemplate
from app.modules.notes.models import Note
from app.modules.pipeline.models import ApplicationStageHistory, PipelineStage
from app.modules.tags.models import ApplicationTag, Tag
from app.modules.users.models import User

# ═════════════════════════════════════════════════════════════════════════════
# Seed data definitions
# ═════════════════════════════════════════════════════════════════════════════

PIPELINE_STAGES = [
    ("Applied",   1),
    ("Screening", 2),
    ("Interview", 3),
    ("Offer",     4),
    ("Hired",     5),
    ("Rejected",  6),
]

COMPANIES = [
    {"name": "Acme Technologies"},
    {"name": "NovaSoft"},
]

USERS = [
    # (company_index, email, password, role)
    (0, "owner@acme.com",     "Password123!", "owner"),
    (0, "recruiter@acme.com", "Password123!", "recruiter"),
    (0, "manager@acme.com",   "Password123!", "manager"),
    (1, "owner@novasoft.com", "Password123!", "owner"),
]

JOBS = [
    # (company_index, title, department, location, status, description)
    (0, "Senior Backend Engineer",    "Engineering",  "Warsaw, Poland",   "open",
     "We are looking for a senior Python/FastAPI developer to join our growing team."),
    (0, "Frontend Developer (React)", "Engineering",  "Remote",           "open",
     "Build beautiful, performant UIs with React and TypeScript."),
    (0, "Product Manager",            "Product",      "Warsaw, Poland",   "open",
     "Drive product strategy and work closely with engineering teams."),
    (0, "UX Designer",                "Design",       "Krakow, Poland",   "draft",
     "Create intuitive user experiences for our SaaS products."),
    (0, "DevOps Engineer",            "Infrastructure","Remote",          "closed",
     "Manage our cloud infrastructure on AWS with Terraform and Kubernetes."),
    (1, "Full Stack Developer",       "Engineering",  "Gdansk, Poland",   "open",
     "Work across the entire stack — Django backend and Vue.js frontend."),
    (1, "Data Analyst",               "Analytics",    "Remote",           "open",
     "Turn raw data into actionable insights using Python and SQL."),
]

TAGS = [
    # (company_index, name)
    (0, "python"),    (0, "react"),     (0, "senior"),
    (0, "remote"),    (0, "recommended"),(0, "fast-learner"),
    (1, "django"),    (1, "vue"),        (1, "data"),
]

CANDIDATES = [
    ("Jan",      "Kowalski",   "jan.kowalski@example.com",   "+48 600 100 200"),
    ("Anna",     "Nowak",      "anna.nowak@example.com",     "+48 601 200 300"),
    ("Piotr",    "Wiśniewski", "piotr.w@example.com",        "+48 602 300 400"),
    ("Katarzyna","Wójcik",     "kasia.wojcik@example.com",   "+48 603 400 500"),
    ("Michał",   "Kamiński",   "michal.k@example.com",       "+48 604 500 600"),
    ("Agnieszka","Lewandowska","agnieszka.l@example.com",    "+48 605 600 700"),
    ("Tomasz",   "Zieliński",  "tomasz.z@example.com",       "+48 606 700 800"),
    ("Marta",    "Szymańska",  "marta.sz@example.com",       "+48 607 800 900"),
    ("Łukasz",   "Woźniak",    "lukasz.w@example.com",       None),
    ("Zofia",    "Dąbrowska",  "zofia.d@example.com",        "+48 609 000 100"),
]

NOTES_CONTENT = [
    "Strong technical background, impressive portfolio. Definitely worth moving forward.",
    "Good communication skills, needs to improve system design knowledge.",
    "Excellent culture fit. Team loved them during the informal chat.",
    "Salary expectations are above our budget. Negotiation needed.",
    "Had a great technical interview — solved all problems efficiently.",
    "References checked — all positive feedback from previous employers.",
    "Needs more experience with distributed systems but shows great potential.",
    "Very motivated candidate, proactive in asking questions about the role.",
]

FORM_FIELDS = [
    {"label": "Years of experience", "field_type": "number", "required": True},
    {"label": "Current company",     "field_type": "text",   "required": False},
    {"label": "Notice period",       "field_type": "select", "required": True,
     "options": ["Immediately", "2 weeks", "1 month", "3 months"]},
    {"label": "Cover letter",        "field_type": "textarea","required": False},
    {"label": "Expected salary (PLN/month)", "field_type": "number", "required": True},
    {"label": "LinkedIn profile",    "field_type": "text",   "required": False},
    {"label": "Available for remote","field_type": "checkbox","required": False},
]


# ═════════════════════════════════════════════════════════════════════════════
# Seeder
# ═════════════════════════════════════════════════════════════════════════════

class Seeder:
    def __init__(self, session: AsyncSession):
        self.db = session
        self.companies: list[Company] = []
        self.users: list[User] = []
        self.stages: list[PipelineStage] = []
        self.jobs: list[Job] = []
        self.tags: list[Tag] = []
        self.templates: list[FormTemplate] = []

    async def run(self, fresh: bool = False, stages_only: bool = False):
        if fresh:
            await self._truncate_all()

        await self._seed_stages()
        if stages_only:
            print("✅ Pipeline stages seeded.")
            return

        await self._seed_companies()
        await self._seed_users()
        await self._seed_tags()
        await self._seed_form_templates()
        await self._seed_jobs()
        await self._seed_applications()
        await self.db.commit()
        print("\n✅ Database seeded successfully!\n")
        self._print_credentials()

    # ------------------------------------------------------------------
    # Truncate
    # ------------------------------------------------------------------
    async def _truncate_all(self):
        print("🗑  Truncating all tables...")
        tables = [
            "audit_logs", "application_tags", "candidate_scores",
            "application_stage_history", "application_answers", "notes",
            "applications", "job_form_templates", "form_fields",
            "form_templates", "tags", "refresh_tokens", "jobs",
            "users", "companies", "pipeline_stages",
        ]
        for table in tables:
            await self.db.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
        await self.db.commit()
        print("✅ Tables truncated.\n")

    # ------------------------------------------------------------------
    # Pipeline stages
    # ------------------------------------------------------------------
    async def _seed_stages(self):
        # Check if already exist
        result = await self.db.execute(text("SELECT COUNT(*) FROM pipeline_stages"))
        count = result.scalar()
        if count and count > 0:
            print(f"⏭  Pipeline stages already exist ({count}), skipping.")
            result2 = await self.db.execute(text("SELECT id, name, order_index FROM pipeline_stages ORDER BY order_index"))
            rows = result2.fetchall()
            for row in rows:
                stage = PipelineStage()
                stage.id = row[0]
                stage.name = row[1]
                stage.order_index = row[2]
                self.stages.append(stage)
            return

        print("🌱 Seeding pipeline stages...")
        for name, order in PIPELINE_STAGES:
            stage = PipelineStage(name=name, order_index=order)
            self.db.add(stage)
            self.stages.append(stage)
        await self.db.flush()
        print(f"   Created {len(self.stages)} stages.")

    # ------------------------------------------------------------------
    # Companies
    # ------------------------------------------------------------------
    async def _seed_companies(self):
        print("🌱 Seeding companies...")
        for data in COMPANIES:
            company = Company(name=data["name"])
            self.db.add(company)
            self.companies.append(company)
        await self.db.flush()
        print(f"   Created {len(self.companies)} companies.")

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    async def _seed_users(self):
        print("🌱 Seeding users...")
        for company_idx, email, password, role in USERS:
            user = User(
                company_id=self.companies[company_idx].id,
                email=email,
                password_hash=hash_password(password),
                role=role,
                is_verified=True,
            )
            self.db.add(user)
            self.users.append(user)
        await self.db.flush()
        print(f"   Created {len(self.users)} users.")

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------
    async def _seed_tags(self):
        print("🌱 Seeding tags...")
        for company_idx, name in TAGS:
            tag = Tag(company_id=self.companies[company_idx].id, name=name)
            self.db.add(tag)
            self.tags.append(tag)
        await self.db.flush()
        print(f"   Created {len(self.tags)} tags.")

    # ------------------------------------------------------------------
    # Form templates
    # ------------------------------------------------------------------
    async def _seed_form_templates(self):
        print("🌱 Seeding form templates...")
        for company in self.companies:
            template = FormTemplate(
                company_id=company.id,
                name="Standard Application Form",
            )
            self.db.add(template)
            await self.db.flush()

            for i, field_data in enumerate(FORM_FIELDS):
                field = FormField(
                    template_id=template.id,
                    label=field_data["label"],
                    field_type=field_data["field_type"],
                    required=field_data.get("required", False),
                    options=field_data.get("options"),
                    order_index=i,
                )
                self.db.add(field)
            self.templates.append(template)

        await self.db.flush()
        print(f"   Created {len(self.templates)} templates with fields.")

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------
    async def _seed_jobs(self):
        print("🌱 Seeding jobs...")
        for company_idx, title, dept, location, status, desc in JOBS:
            job = Job(
                company_id=self.companies[company_idx].id,
                title=title,
                department=dept,
                location=location,
                status=status,
                description=desc,
            )
            self.db.add(job)
            await self.db.flush()

            # Link form template
            template = next(
                (t for t in self.templates if t.company_id == self.companies[company_idx].id),
                None
            )
            if template:
                link = JobFormTemplate(job_id=job.id, template_id=template.id)
                self.db.add(link)

            self.jobs.append(job)

        await self.db.flush()
        print(f"   Created {len(self.jobs)} jobs.")

    # ------------------------------------------------------------------
    # Applications
    # ------------------------------------------------------------------
    async def _seed_applications(self):
        print("🌱 Seeding applications...")

        # Only apply to open jobs
        open_jobs = [j for j in self.jobs if j.status == "open"]
        acme_users = [u for u in self.users if u.company_id == self.companies[0].id]
        acme_tags = [t for t in self.tags if t.company_id == self.companies[0].id]

        app_count = 0
        stage_map = {s.name: s for s in self.stages}

        # Distribute candidates across open jobs with varying stages
        stage_progression = [
            "Applied", "Screening", "Interview", "Offer", "Hired",
            "Rejected", "Applied", "Screening", "Interview", "Applied",
        ]

        for i, (first, last, email, phone) in enumerate(CANDIDATES):
            job = open_jobs[i % len(open_jobs)]
            stage_name = stage_progression[i]
            stage = stage_map.get(stage_name)

            # Find the recruiter for this company
            recruiter = next(
                (u for u in acme_users if u.role in ("owner", "recruiter")),
                acme_users[0]
            )

            app = Application(
                job_id=job.id,
                first_name=first,
                last_name=last,
                email=email,
                phone=phone,
                stage_id=stage.id if stage else None,
                public_token=generate_public_token(),
                created_at=datetime.now(UTC) - timedelta(days=30 - i * 2),
            )
            self.db.add(app)
            await self.db.flush()

            # Stage history — record all stages up to current
            stage_order = ["Applied", "Screening", "Interview", "Offer", "Hired", "Rejected"]
            current_idx = stage_order.index(stage_name) if stage_name in stage_order else 0
            for si in range(current_idx + 1):
                history = ApplicationStageHistory(
                    application_id=app.id,
                    stage_id=stage_map[stage_order[si]].id,
                    changed_by=recruiter.id,
                    changed_at=datetime.now(UTC) - timedelta(days=28 - i * 2 - si),
                )
                self.db.add(history)

            # Form answers
            answer = ApplicationAnswer(
                application_id=app.id,
                field_id=(await self._get_first_field(job.id)),
                value=str(i + 2),  # years of experience
            )
            if answer.field_id:
                self.db.add(answer)

            # Notes (every other candidate)
            if i % 2 == 0:
                note = Note(
                    application_id=app.id,
                    author_id=recruiter.id,
                    content=NOTES_CONTENT[i % len(NOTES_CONTENT)],
                    visible_to_candidate=False,
                )
                self.db.add(note)

            # Scores (for candidates past screening)
            if stage_name not in ("Applied",):
                score = CandidateScore(
                    application_id=app.id,
                    recruiter_id=recruiter.id,
                    communication=3 + (i % 3),
                    technical=2 + (i % 4),
                    culture_fit=3 + (i % 3),
                )
                self.db.add(score)

            # Tags (first 2 tags for even candidates)
            if i < len(acme_tags):
                app_tag = ApplicationTag(
                    application_id=app.id,
                    tag_id=acme_tags[i % len(acme_tags)].id,
                )
                self.db.add(app_tag)

            # Audit log
            audit = AuditLog(
                company_id=job.company_id,
                user_id=recruiter.id,
                action="application_received",
                entity_type="application",
                entity_id=app.id,
            )
            self.db.add(audit)

            app_count += 1

        await self.db.flush()
        print(f"   Created {app_count} applications with history, notes, scores and tags.")

    async def _get_first_field(self, job_id: uuid.UUID):
        """Get first form field for a job's template."""
        result = await self.db.execute(
            text("""
                SELECT ff.id FROM form_fields ff
                JOIN job_form_templates jft ON jft.template_id = ff.template_id
                WHERE jft.job_id = :job_id
                ORDER BY ff.order_index
                LIMIT 1
            """),
            {"job_id": job_id}
        )
        row = result.fetchone()
        return row[0] if row else None

    def _print_credentials(self):
        print("=" * 50)
        print("🔑 Login credentials:")
        print("=" * 50)
        for company_idx, email, password, role in USERS:
            company = COMPANIES[company_idx]["name"]
            print(f"  [{company}] {email} / {password}  ({role})")
        print("=" * 50)


# ═════════════════════════════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════════════════════════════

async def main():
    fresh = "--fresh" in sys.argv
    stages_only = "--stages" in sys.argv

    engine = create_async_engine(settings.database_url, echo=False)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as session:
        seeder = Seeder(session)
        await seeder.run(fresh=fresh, stages_only=stages_only)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())