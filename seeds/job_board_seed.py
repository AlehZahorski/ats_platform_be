"""Job board seed — populates the public-facing wakanta.pl job board with
realistic volume so the UI can be tested at scale.

Generates:
  • ~200 companies with varied names (mix verified / not verified)
  • One owner user per company (uses dummy emails)
  • 20–40 random jobs per category (×172 categories) → ~5000 open jobs
  • Realistic field distributions (salary, work_mode, seniority, location)

Run inside the backend container:

    docker compose exec backend python seeds/job_board_seed.py
    docker compose exec backend python seeds/job_board_seed.py --reset   # wipe job-board seed data first

Idempotent: re-running without --reset will just append more jobs.
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

# Import ALL model modules so SQLAlchemy can resolve cross-module relationships
# before flush. Without this, lazy resolution of "FormTemplate", "Application",
# etc. fails. We import modules (not classes) so we don't need to know the
# exact class names of each.
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


# ──────────────────────────────────────────────────────────────────────
# Static data
# ──────────────────────────────────────────────────────────────────────

CITY_POOL = [
    "Warszawa", "Kraków", "Wrocław", "Poznań", "Gdańsk", "Łódź", "Katowice",
    "Szczecin", "Lublin", "Białystok", "Bydgoszcz", "Toruń", "Rzeszów", "Olsztyn",
    "Berlin", "Praga", "Wiedeń", "Amsterdam", "Londyn", "Dublin", "Sztokholm",
]

COMPANY_PREFIXES = ["Soft", "Tech", "Code", "Cloud", "Data", "Pixel", "Quantum", "Alpha",
                    "Nordic", "Vertex", "Apex", "Stellar", "Northern", "Polish", "European",
                    "BlueSky", "GreenLeaf", "Iron", "Silver", "Golden", "Crystal"]
COMPANY_SUFFIXES = ["Labs", "Studios", "Works", "Solutions", "Systems", "Group", "Holdings",
                    "Industries", "Partners", "Logistics", "Healthcare", "Media", "Foods",
                    "Pharma", "Construction", "Energy", "Transport"]

CATEGORIES: list[str] = [
    # ── Tech (22)
    "it_backend","it_frontend","it_fullstack","it_mobile","it_embedded","it_gamedev","it_devops",
    "it_cloud_architect","it_cybersecurity","it_data_engineer","it_data_scientist","it_bi_analyst",
    "it_qa_manual","it_qa_automation","it_helpdesk","it_sysadmin","it_network","it_dba",
    "it_tech_pm","it_scrum_master","it_technical_writer","it_solutions_architect",
    # Design (10)
    "design_uxui","design_product","design_graphic","design_industrial","design_motion",
    "design_video_editing","design_3d_vfx","design_game","design_brand","design_illustration",
    # Marketing (14)
    "marketing_manager","marketing_digital","marketing_content","marketing_seo_sem",
    "marketing_social_media","marketing_performance","marketing_ecommerce_mgr","marketing_growth",
    "marketing_pr","marketing_copywriting","marketing_brand","marketing_event","marketing_email","marketing_influencer",
    # Sales (12)
    "sales_manager","sales_account_executive","sales_account_manager","sales_sdr","sales_bizdev",
    "sales_inside","sales_field","sales_retail","sales_engineer","sales_channel","sales_presales","sales_telesales",
    # Customer service (6)
    "cs_rep","cs_customer_success","cs_call_center","cs_tech_support","cs_receptionist","cs_concierge",
    # Finance (17)
    "fin_accountant","fin_analyst","fin_controller","fin_cfo","fin_tax","fin_audit","fin_treasury",
    "fin_banking_retail","fin_banking_investment","fin_banking_corporate","fin_insurance_agent",
    "fin_underwriter","fin_actuary","fin_risk","fin_aml_compliance","fin_debt_collection","fin_payroll",
    # HR (8)
    "hr_generalist","hr_recruiter","hr_manager","hr_compben","hr_learning_dev",
    "hr_employer_branding","hr_hris","hr_payroll_admin",
    # Legal (8)
    "legal_lawyer","legal_paralegal","legal_in_house_counsel","legal_contract",
    "legal_notary","legal_compliance","legal_ip_patent","legal_tax_lawyer",
    # Operations (10)
    "ops_manager","ops_project_manager","ops_program_manager","ops_business_analyst",
    "ops_process_engineer","ops_lean_sixsigma","ops_procurement","ops_buyer",
    "ops_category_manager","ops_vendor_mgmt",
    # Logistics (11)
    "log_coordinator","log_freight_forwarder","log_warehouse_manager","log_warehouse_op",
    "log_inventory","log_driver_heavy","log_driver_light","log_driver_bus","log_courier",
    "log_train_operator","log_customs",
    # Manufacturing (13)
    "mfg_operator","mfg_team_leader","mfg_manager","mfg_cnc_operator","mfg_welder",
    "mfg_machine_operator","mfg_assembly","mfg_plant_manager","mfg_maintenance",
    "mfg_industrial_mechanic","mfg_industrial_electrician","mfg_tool_mold_maker","mfg_painter",
    # Construction (14)
    "con_worker","con_foreman","con_manager","con_carpenter","con_electrician","con_plumber",
    "con_hvac","con_mason","con_roofer","con_tiler","con_concrete","con_glazier",
    "con_surveyor","con_architect_assistant",
    # Engineering (13)
    "eng_mechanical","eng_electrical","eng_civil","eng_chemical","eng_environmental",
    "eng_automation_robotics","eng_industrial","eng_aerospace","eng_mining","eng_telco",
    "eng_energy","eng_marine","eng_quality",
    # Healthcare (24)
    "hc_physician_gp","hc_physician_specialist","hc_surgeon","hc_nurse_registered","hc_nurse_practical",
    "hc_paramedic","hc_physiotherapist","hc_occupational_therapist","hc_speech_therapist",
    "hc_dentist","hc_dental_hygienist","hc_pharmacist","hc_pharmacy_tech","hc_psychologist",
    "hc_psychotherapist","hc_psychiatrist","hc_caregiver","hc_veterinarian","hc_vet_technician",
    "hc_dietitian","hc_lab_technician","hc_xray_technician","hc_optometrist","hc_midwife",
    # Education (14)
    "edu_preschool_teacher","edu_primary_teacher","edu_secondary_teacher","edu_sped_teacher",
    "edu_university_lecturer","edu_professor_researcher","edu_vocational_trainer",
    "edu_language_tutor","edu_music_teacher","edu_sports_coach","edu_private_tutor",
    "edu_school_counselor","edu_childcare_nanny","edu_librarian",
    # Hospitality (14)
    "hsp_chef","hsp_cook","hsp_sous_chef","hsp_pastry_chef","hsp_baker","hsp_waiter","hsp_bartender",
    "hsp_barista","hsp_hotel_receptionist","hsp_hotel_manager","hsp_housekeeping",
    "hsp_tour_guide","hsp_travel_agent","hsp_restaurant_manager",
    # Retail (8)
    "ret_cashier","ret_sales_associate","ret_store_manager","ret_visual_merchandiser",
    "ret_buyer_merchandiser","ret_stockroom","ret_florist","ret_pharmacy_counter",
    # Beauty (9)
    "bty_hairdresser","bty_beautician","bty_nail_technician","bty_makeup_artist",
    "bty_massage_therapist","bty_tattoo_artist","bty_spa_therapist","bty_personal_trainer","bty_yoga_instructor",
    # Cleaning (10)
    "cln_residential_cleaner","cln_commercial_cleaner","cln_janitor","cln_window_cleaner",
    "cln_property_manager","cln_building_super","cln_gardener","cln_landscaper",
    "cln_pest_control","cln_real_estate_agent",
    # Security (8)
    "sec_security_guard","sec_bodyguard","sec_cash_in_transit","sec_private_investigator",
    "sec_police","sec_firefighter","sec_military","sec_customs_officer",
    # Media (17)
    "med_journalist","med_editor","med_photographer","med_videographer","med_sound_engineer",
    "med_music_producer","med_musician","med_actor","med_voice_actor","med_radio_host",
    "med_film_production","med_author","med_translator","med_interpreter","med_localization",
    "med_curator","med_art_director",
    # Science (9)
    "sci_research_scientist","sci_lab_technician","sci_biologist","sci_chemist","sci_physicist",
    "sci_geologist","sci_statistician","sci_mathematician","sci_social_scientist",
    # Agriculture (9)
    "agr_farm_worker","agr_farm_manager","agr_agronomist","agr_beekeeper","agr_forestry",
    "agr_lumberjack","agr_fisherman","agr_aquaculture","agr_horticulturist",
    # Automotive (7)
    "auto_mechanic","auto_electrician","auto_body_repair","auto_painter","auto_service_advisor",
    "auto_inspector","auto_tire_tech",
    # Energy (8)
    "enr_power_plant_op","enr_linesman","enr_gas_technician","enr_water_treatment",
    "enr_solar_installer","enr_wind_turbine_tech","enr_mining_worker","enr_oil_gas",
    # Government (6)
    "gov_public_admin","gov_municipal_worker","gov_civil_servant","gov_postal_worker",
    "gov_diplomat","gov_tax_officer",
]

# Per-category salary range hints (PLN/month or PLN/hour based on character of work)
# Format: (min_low, min_high, max_low, max_high, period)
SALARY_HINTS: dict[str, tuple[int, int, int, int, str]] = {
    # IT — high paid
    "it_backend": (8000, 18000, 15000, 35000, "month"),
    "it_devops": (10000, 20000, 18000, 38000, "month"),
    "it_data_scientist": (12000, 22000, 22000, 40000, "month"),
    # Trades — hourly
    "mfg_operator": (25, 35, 32, 50, "hour"),
    "log_driver_heavy": (5500, 7500, 8000, 12000, "month"),
    "hsp_waiter": (22, 30, 28, 45, "hour"),
    "cln_residential_cleaner": (25, 32, 30, 45, "hour"),
    # Healthcare
    "hc_physician_gp": (10000, 16000, 18000, 30000, "month"),
    "hc_nurse_registered": (5500, 7500, 8000, 12000, "month"),
    # Education
    "edu_preschool_teacher": (3800, 5000, 5500, 7500, "month"),
    "edu_secondary_teacher": (4200, 5500, 6000, 8500, "month"),
    # CFO
    "fin_cfo": (20000, 35000, 40000, 80000, "month"),
}

DEFAULT_SALARY = (4500, 7000, 7500, 12000, "month")

# Work modes per category prefix
ONSITE_PREFIXES = ("mfg_", "con_", "hsp_", "ret_", "bty_", "cln_", "sec_", "agr_", "auto_",
                   "enr_", "log_warehouse", "log_driver", "log_courier", "log_train", "edu_",
                   "hc_")

WORK_MODES_REMOTE_OK = ["office", "hybrid", "remote"]
WORK_MODES_ONSITE = ["office"]


# ──────────────────────────────────────────────────────────────────────
# Generators
# ──────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    only_ascii = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = only_ascii.lower().replace("ł", "l")
    out = ""
    for ch in cleaned:
        out += ch if ch.isalnum() else "-"
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:80]


def random_salary(category: str) -> dict[str, Any]:
    if random.random() < 0.15:
        # 15% undisclosed
        return {"salary_min": None, "salary_max": None, "salary_currency": "PLN", "salary_period": "month"}
    hint = SALARY_HINTS.get(category, DEFAULT_SALARY)
    min_low, min_high, max_low, max_high, period = hint
    smin = random.randint(min_low, min_high)
    # Ensure max is at least slightly higher than min — delta scales with period
    delta = 5 if period == "hour" else 500
    smax = random.randint(max(smin + delta, max_low), max(smin + delta * 2, max_high))
    return {"salary_min": smin, "salary_max": smax, "salary_currency": "PLN", "salary_period": period}


def random_work_mode(category: str) -> str:
    if any(category.startswith(p) for p in ONSITE_PREFIXES):
        return "office"
    return random.choice(WORK_MODES_REMOTE_OK)


def random_company_name() -> str:
    return f"{random.choice(COMPANY_PREFIXES)}{random.choice(COMPANY_SUFFIXES)}"


def random_techstack() -> str:
    pool = ["Python", "Django", "FastAPI", "PostgreSQL", "Redis", "Docker", "Kubernetes",
            "AWS", "GCP", "Azure", "React", "TypeScript", "Next.js", "Tailwind",
            "Node.js", "Go", "Rust", "Java", "Spring Boot", "Kafka", "Elasticsearch"]
    picked = random.sample(pool, k=random.randint(3, 6))
    items = "".join(f"<li>{p}</li>" for p in picked)
    return f"<ul>{items}</ul>"


def random_responsibilities(category: str) -> str:
    samples = [
        "Współpraca z zespołem produktowym i programistycznym",
        "Projektowanie i wdrażanie nowych funkcjonalności",
        "Code review i mentoring młodszych członków zespołu",
        "Analiza wymagań biznesowych i przygotowanie dokumentacji",
        "Optymalizacja istniejących procesów i systemów",
        "Udział w spotkaniach planistycznych i retrospektywach",
        "Kontrola jakości realizowanych zadań",
        "Raportowanie postępów do bezpośredniego przełożonego",
        "Współpraca z klientem wewnętrznym i zewnętrznym",
        "Wdrażanie standardów branżowych i procedur bezpieczeństwa",
    ]
    picked = random.sample(samples, k=random.randint(3, 5))
    items = "".join(f"<li>{p}</li>" for p in picked)
    return f"<ul>{items}</ul>"


def random_must_haves() -> str:
    pool = [
        "Doświadczenie min. 2 lata na podobnym stanowisku",
        "Znajomość języka angielskiego (B2)",
        "Umiejętność pracy w zespole",
        "Zaangażowanie i samodzielność",
        "Wykształcenie wyższe kierunkowe",
        "Komunikatywność i otwartość",
        "Umiejętność rozwiązywania problemów",
        "Znajomość branży",
    ]
    picked = random.sample(pool, k=random.randint(3, 5))
    items = "".join(f"<li>{p}</li>" for p in picked)
    return f"<ul>{items}</ul>"


def random_benefits() -> str:
    pool = [
        "Prywatna opieka medyczna (Luxmed)",
        "Karta sportowa Multisport",
        "Ubezpieczenie grupowe",
        "Premia kwartalna uzależniona od wyników",
        "Możliwość pracy zdalnej",
        "Elastyczne godziny pracy",
        "Budżet szkoleniowy 5000 PLN rocznie",
        "Owoce i przekąski w biurze",
        "Spotkania integracyjne firmowe",
        "Dofinansowanie nauki języków obcych",
        "Sprzęt klasy premium (MacBook Pro / Dell)",
        "Wsparcie psychologiczne",
    ]
    picked = random.sample(pool, k=random.randint(3, 6))
    items = "".join(f"<li>{p}</li>" for p in picked)
    return f"<ul>{items}</ul>"


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

async def main(reset: bool = False) -> None:
    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        if reset:
            print("⚠ Wiping job_board seed data…")
            await db.execute(text("DELETE FROM jobs WHERE company_id IN (SELECT id FROM companies WHERE name LIKE '%(seeded)%')"))
            await db.execute(text("DELETE FROM users WHERE company_id IN (SELECT id FROM companies WHERE name LIKE '%(seeded)%')"))
            await db.execute(text("DELETE FROM companies WHERE name LIKE '%(seeded)%'"))
            await db.commit()

        # Create ~200 companies. Tag with "(seeded)" so reset can find them.
        print("Creating 200 companies…")
        companies: list[Company] = []
        for i in range(200):
            name = f"{random_company_name()} {random.randint(10, 9999)} (seeded)"
            company = Company(name=name, is_verified=random.random() < 0.6)  # 60% verified
            db.add(company)
            companies.append(company)
        await db.flush()

        # One owner user per company so jobs.created_by has someone
        print("Creating owner users…")
        password_hash = hash_password("password123")
        for company in companies:
            owner = User(
                company_id=company.id,
                email=f"owner-{company.id}@seeded.local",
                password_hash=password_hash,
                role="owner",
                is_verified=True,
                language="pl",
            )
            db.add(owner)
        await db.flush()

        # Jobs: 20-40 per category, distributed across random companies
        total_jobs = 0
        print(f"Creating jobs across {len(CATEGORIES)} categories…")
        for category in CATEGORIES:
            count = random.randint(20, 40)
            for _ in range(count):
                company = random.choice(companies)
                title_base = category.replace("_", " ").title()
                seniority_levels = ["junior", "mid", "senior", "specialist", "operator", None]
                seniority = random.choice(seniority_levels)
                title = f"{seniority.capitalize() + ' ' if seniority else ''}{title_base}"

                salary = random_salary(category)
                location = random.choice(CITY_POOL)
                slug = f"{slugify(title)}-{location.lower()[:6]}-{uuid.uuid4().hex[:6]}"

                job = Job(
                    company_id=company.id,
                    title=title,
                    slug=slug,
                    department=None,
                    location=location,
                    status="open",
                    category=category,
                    work_mode=random_work_mode(category),
                    contract_type=random.choice(["employment", "b2b", "contract"]),
                    seniority=seniority,
                    employment_size=random.choice(["full", "full", "full", "part_75", "part_50"]),
                    role_summary=f"Poszukujemy osoby na stanowisko {title.lower()} z doświadczeniem branżowym. "
                                 f"Dołącz do dynamicznego zespołu i rozwijaj się razem z nami.",
                    responsibilities=random_responsibilities(category),
                    must_haves=random_must_haves(),
                    tech_stack=random_techstack() if category.startswith("it_") else None,
                    benefits=random_benefits(),
                    required_qualifications=[],
                    **salary,
                )
                # Stagger created_at to make "newest" sort meaningful
                job.created_at = datetime.now(UTC) - timedelta(hours=random.randint(0, 720))
                db.add(job)
                total_jobs += 1
            # Periodic flush to avoid memory blowup
            if total_jobs % 500 == 0:
                await db.flush()
                print(f"  …{total_jobs} jobs so far")

        await db.commit()
        print(f"✓ Done. Total jobs created: {total_jobs}, companies: {len(companies)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Wipe seeded data first")
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset))
