"""Realistic job-board seed.

Replaces the random `job_board_seed.py` data with 25 hand-crafted companies:
  - 20 in-house employers across different industries (production, IT,
    healthcare, hospitality, etc.)
  - 5 HR/recruitment agencies that post listings for various client companies
  - Mix of Polish and English companies + job ads (mirrors real PL market)
  - Each company gets ~5-15 realistic openings matching its profile
  - Predictable login credentials for navigation/demos (see README.md)

Run inside the backend container:

    docker compose exec backend python seeds/realistic_seed.py
    docker compose exec backend python seeds/realistic_seed.py --reset

`--reset` wipes the previous job-board seed (companies tagged "(seeded)" or
"(demo)") before recreating.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import uuid
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, ".")
from app.core.config import settings
from app.core.security import hash_password

# Import all model modules for relationship resolution
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
from app.modules.forms.models import FormField, FormTemplate
from app.modules.jobs.models import Job, JobFormTemplate
from app.modules.users.models import User


DEMO_PASSWORD = "demo1234"


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def slugify(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    only_ascii = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = only_ascii.lower().replace("ł", "l").replace("ß", "ss")
    out = ""
    for ch in cleaned:
        out += ch if ch.isalnum() else "-"
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:80]


def ul(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def ol(items: list[str]) -> str:
    return "<ol>" + "".join(f"<li>{i}</li>" for i in items) + "</ol>"


# ──────────────────────────────────────────────────────────────────────
# Company definitions
# ──────────────────────────────────────────────────────────────────────

# Each tuple: (display_name, slug, language_label, is_verified, profile_blurb, jobs[])
# Each job: dict with fields matching Job model. Reasonable defaults applied
# in the main loop for missing optional fields.

COMPANIES: list[dict[str, Any]] = [
    # ── 1. PolMet S.A. — manufacturing/metalworking (PL)
    {
        "name": "PolMet S.A.",
        "slug": "polmet",
        "lang": "pl",
        "verified": True,
        "blurb": "Krajowy producent precyzyjnych odlewów i komponentów stalowych dla branż automotive, kolejowej i energetycznej. Zakłady w Katowicach i Gliwicach.",
        "jobs": [
            {"title": "Operator CNC", "category": "mfg_cnc_operator", "seniority": "operator", "loc": "Katowice", "salary": (5500, 8500), "shift": "two_shift"},
            {"title": "Spawacz MAG/MIG", "category": "mfg_welder", "seniority": "worker", "loc": "Gliwice", "salary": (5000, 7800), "shift": "two_shift"},
            {"title": "Brygadzista produkcji", "category": "mfg_team_leader", "seniority": "team_leader", "loc": "Katowice", "salary": (7000, 10000), "shift": "three_shift"},
            {"title": "Mechanik utrzymania ruchu", "category": "mfg_maintenance", "seniority": "worker", "loc": "Katowice", "salary": (6500, 9500)},
            {"title": "Elektryk przemysłowy", "category": "mfg_industrial_electrician", "seniority": "worker", "loc": "Gliwice", "salary": (6800, 10000), "quals": ["sep_g1", "sep_g2"]},
            {"title": "Operator linii lakierniczej", "category": "mfg_painter", "seniority": "operator", "loc": "Katowice", "salary": (5000, 7500), "shift": "two_shift"},
            {"title": "Kontroler jakości", "category": "mfg_assembly", "seniority": "specialist", "loc": "Gliwice", "salary": (6500, 9000)},
            {"title": "Kierownik produkcji", "category": "mfg_manager", "seniority": "manager", "loc": "Katowice", "salary": (13000, 18000)},
        ],
    },
    # ── 2. GreenLine Sp. z o.o. — food production (PL)
    {
        "name": "GreenLine Sp. z o.o.",
        "slug": "greenline",
        "lang": "pl",
        "verified": True,
        "blurb": "Producent mrożonych warzyw i owoców pod markami własnymi sieci handlowych. Zakład w Poznaniu, 320 osób załogi.",
        "jobs": [
            {"title": "Pracownik produkcji żywności", "category": "mfg_operator", "seniority": "worker", "loc": "Poznań", "salary": (4500, 6200), "shift": "three_shift", "quals": ["health_card", "haccp"]},
            {"title": "Operator linii pakującej", "category": "mfg_machine_operator", "seniority": "operator", "loc": "Poznań", "salary": (4800, 6800), "shift": "two_shift", "quals": ["health_card"]},
            {"title": "Magazynier chłodni", "category": "log_warehouse_op", "seniority": "worker", "loc": "Poznań", "salary": (5000, 7000), "quals": ["forklift_udt", "health_card"]},
            {"title": "Brygadzista zmiany", "category": "mfg_team_leader", "seniority": "team_leader", "loc": "Poznań", "salary": (6500, 9000), "shift": "three_shift"},
            {"title": "Technolog żywności", "category": "fin_quality_analyst" if False else "sci_chemist", "seniority": "specialist", "loc": "Poznań", "salary": (7500, 11000)},
            {"title": "Kierownik zmiany", "category": "mfg_manager", "seniority": "manager", "loc": "Poznań", "salary": (10000, 14000), "shift": "three_shift"},
        ],
    },
    # ── 3. TechVibes Studio — software house (EN)
    {
        "name": "TechVibes Studio",
        "slug": "techvibes",
        "lang": "en",
        "verified": True,
        "blurb": "Product engineering studio building SaaS for European mid-market clients. Fully remote-first team of 65, HQ in Wrocław.",
        "jobs": [
            {"title": "Senior Backend Engineer (Python)", "category": "it_backend", "seniority": "senior", "loc": "Remote (EU)", "salary": (18000, 26000), "work_mode": "remote", "techs": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "AWS"]},
            {"title": "Senior Frontend Engineer (React)", "category": "it_frontend", "seniority": "senior", "loc": "Remote (EU)", "salary": (17000, 25000), "work_mode": "remote", "techs": ["React", "TypeScript", "Next.js", "Tailwind"]},
            {"title": "Fullstack Developer", "category": "it_fullstack", "seniority": "mid", "loc": "Wrocław", "salary": (13000, 19000), "work_mode": "hybrid", "techs": ["TypeScript", "Node.js", "React", "PostgreSQL"]},
            {"title": "DevOps Engineer (AWS)", "category": "it_devops", "seniority": "senior", "loc": "Remote (EU)", "salary": (20000, 28000), "work_mode": "remote", "techs": ["AWS", "Terraform", "Kubernetes", "GitHub Actions"], "quals": ["aws_cert"]},
            {"title": "QA Automation Engineer", "category": "it_qa_automation", "seniority": "mid", "loc": "Wrocław", "salary": (12000, 17000), "work_mode": "hybrid", "techs": ["Playwright", "TypeScript", "Pytest"]},
            {"title": "Mobile Developer (iOS)", "category": "it_mobile", "seniority": "senior", "loc": "Remote (EU)", "salary": (16000, 23000), "work_mode": "remote", "techs": ["Swift", "SwiftUI", "Combine"]},
            {"title": "Data Engineer", "category": "it_data_engineer", "seniority": "senior", "loc": "Wrocław", "salary": (17000, 24000), "work_mode": "hybrid", "techs": ["Python", "Snowflake", "dbt", "Airflow"]},
            {"title": "ML Engineer", "category": "it_data_scientist", "seniority": "senior", "loc": "Remote (EU)", "salary": (19000, 27000), "work_mode": "remote", "techs": ["Python", "PyTorch", "MLflow", "AWS SageMaker"]},
            {"title": "Engineering Manager", "category": "it_tech_pm", "seniority": "manager", "loc": "Wrocław", "salary": (22000, 32000), "work_mode": "hybrid"},
            {"title": "Solutions Architect", "category": "it_solutions_architect", "seniority": "lead", "loc": "Remote (EU)", "salary": (24000, 34000), "work_mode": "remote", "techs": ["AWS", "Microservices", "EDA"], "quals": ["aws_cert"]},
            {"title": "Junior Frontend Developer", "category": "it_frontend", "seniority": "junior", "loc": "Wrocław", "salary": (7000, 10000), "work_mode": "hybrid", "techs": ["React", "TypeScript"]},
            {"title": "Scrum Master", "category": "it_scrum_master", "seniority": "specialist", "loc": "Remote (EU)", "salary": (12000, 17000), "work_mode": "remote", "quals": ["scrum_cert"]},
        ],
    },
    # ── 4. Velvet Hotels Group — hospitality (EN)
    {
        "name": "Velvet Hotels Group",
        "slug": "velvethotels",
        "lang": "en",
        "verified": True,
        "blurb": "Boutique 4-star hotel chain with properties in Warsaw, Kraków and Gdańsk. Premium service with a focus on staff development.",
        "jobs": [
            {"title": "Hotel Receptionist (Warsaw)", "category": "hsp_hotel_receptionist", "loc": "Warszawa", "salary": (5000, 7000), "shift": "three_shift"},
            {"title": "Hotel Receptionist (Kraków)", "category": "hsp_hotel_receptionist", "loc": "Kraków", "salary": (4800, 6800), "shift": "three_shift"},
            {"title": "Chef de Partie", "category": "hsp_cook", "loc": "Warszawa", "salary": (5500, 8000), "shift": "two_shift", "quals": ["health_card", "haccp"]},
            {"title": "Sous Chef", "category": "hsp_sous_chef", "seniority": "specialist", "loc": "Warszawa", "salary": (7500, 11000), "quals": ["health_card", "haccp"]},
            {"title": "Pastry Chef", "category": "hsp_pastry_chef", "loc": "Kraków", "salary": (6000, 8500), "quals": ["health_card"]},
            {"title": "Bartender", "category": "hsp_bartender", "loc": "Gdańsk", "salary": (5000, 7500), "shift": "weekend", "quals": ["health_card"]},
            {"title": "Housekeeping Staff", "category": "hsp_housekeeping", "loc": "Warszawa", "salary": (4500, 5800), "shift": "two_shift"},
            {"title": "Concierge", "category": "cs_concierge", "loc": "Kraków", "salary": (5500, 7500)},
            {"title": "Hotel Manager", "category": "hsp_hotel_manager", "seniority": "manager", "loc": "Gdańsk", "salary": (16000, 22000)},
            {"title": "F&B Manager", "category": "hsp_restaurant_manager", "seniority": "manager", "loc": "Warszawa", "salary": (13000, 18000)},
        ],
    },
    # ── 5. Krakowski Szpital Specjalistyczny (PL)
    {
        "name": "Krakowski Szpital Specjalistyczny",
        "slug": "kss-krakow",
        "lang": "pl",
        "verified": True,
        "blurb": "Wielospecjalistyczny szpital publiczny z 24-godzinnym SOR. Zatrudniamy ponad 800 osób personelu medycznego.",
        "jobs": [
            {"title": "Lekarz internista", "category": "hc_physician_specialist", "seniority": "attending", "loc": "Kraków", "salary": (18000, 28000), "quals": ["medical_license"]},
            {"title": "Lekarz pediatra", "category": "hc_physician_specialist", "seniority": "attending", "loc": "Kraków", "salary": (17000, 27000), "quals": ["medical_license"]},
            {"title": "Pielęgniarka oddziałowa", "category": "hc_nurse_registered", "seniority": "specialist", "loc": "Kraków", "salary": (8000, 11000), "shift": "three_shift", "quals": ["first_aid"]},
            {"title": "Pielęgniarka SOR", "category": "hc_nurse_registered", "loc": "Kraków", "salary": (7500, 10500), "shift": "three_shift", "quals": ["first_aid"]},
            {"title": "Ratownik medyczny", "category": "hc_paramedic", "loc": "Kraków", "salary": (7000, 9500), "shift": "three_shift", "quals": ["first_aid"]},
            {"title": "Fizjoterapeuta", "category": "hc_physiotherapist", "seniority": "specialist", "loc": "Kraków", "salary": (6500, 9000)},
            {"title": "Położna", "category": "hc_midwife", "loc": "Kraków", "salary": (7500, 10000), "shift": "three_shift", "quals": ["medical_license"]},
            {"title": "Psycholog kliniczny", "category": "hc_psychologist", "seniority": "specialist", "loc": "Kraków", "salary": (8500, 12000)},
            {"title": "Technik elektroradiolog", "category": "hc_xray_technician", "loc": "Kraków", "salary": (6800, 9000), "shift": "two_shift"},
        ],
    },
    # ── 6. Białowieskie Tartaki (PL)
    {
        "name": "Białowieskie Tartaki Sp. z o.o.",
        "slug": "bialowieskie-tartaki",
        "lang": "pl",
        "verified": False,
        "blurb": "Rodzinny tartak z 40-letnią tradycją w obróbce drewna liściastego. Zakład w okolicach Hajnówki.",
        "jobs": [
            {"title": "Operator tartaku", "category": "agr_forestry", "loc": "Hajnówka", "salary": (4800, 6800), "shift": "two_shift", "quals": ["bhp"]},
            {"title": "Drwal", "category": "agr_lumberjack", "loc": "Białowieża", "salary": (5000, 7000), "quals": ["bhp", "driving_b"]},
            {"title": "Pracownik leśny", "category": "agr_forestry", "loc": "Hajnówka", "salary": (4500, 6200), "quals": ["bhp"]},
            {"title": "Kierownik produkcji drewna", "category": "agr_farm_manager", "seniority": "manager", "loc": "Hajnówka", "salary": (9000, 13000)},
            {"title": "Operator suszarni", "category": "mfg_machine_operator", "loc": "Hajnówka", "salary": (5500, 7500), "shift": "two_shift"},
        ],
    },
    # ── 7. Solaris Energia (PL)
    {
        "name": "Solaris Energia S.A.",
        "slug": "solaris-energia",
        "lang": "pl",
        "verified": True,
        "blurb": "Operator farm fotowoltaicznych i wiatrowych w Polsce zachodniej. Łączna moc zainstalowana 280 MW.",
        "jobs": [
            {"title": "Operator elektrowni", "category": "enr_power_plant_op", "loc": "Szczecin", "salary": (6500, 9000), "shift": "three_shift", "quals": ["sep_g1", "sep_g2", "sep_g3"]},
            {"title": "Monter linii energetycznych", "category": "enr_linesman", "loc": "Poznań", "salary": (6000, 8500), "quals": ["sep_g1", "bhp"]},
            {"title": "Instalator paneli fotowoltaicznych", "category": "enr_solar_installer", "loc": "Wrocław", "salary": (5800, 8200), "quals": ["sep_g1"]},
            {"title": "Technik turbin wiatrowych", "category": "enr_wind_turbine_tech", "loc": "Koszalin", "salary": (8000, 12000), "quals": ["bhp"]},
            {"title": "Elektryk SEP G1", "category": "mfg_industrial_electrician", "loc": "Szczecin", "salary": (6500, 9500), "quals": ["sep_g1"]},
            {"title": "Inżynier energetyk", "category": "eng_energy", "seniority": "specialist", "loc": "Szczecin", "salary": (10000, 14000)},
            {"title": "Specjalista BHP w energetyce", "category": "ops_business_analyst", "seniority": "specialist", "loc": "Poznań", "salary": (8000, 11000), "quals": ["bhp"]},
        ],
    },
    # ── 8. DigitalCanvas Agency (EN)
    {
        "name": "DigitalCanvas Agency",
        "slug": "digitalcanvas",
        "lang": "en",
        "verified": True,
        "blurb": "Award-winning digital marketing & design agency working with European SMBs. Hybrid office in Warsaw.",
        "jobs": [
            {"title": "Senior UX Designer", "category": "design_uxui", "seniority": "senior", "loc": "Warszawa", "salary": (15000, 22000), "work_mode": "hybrid"},
            {"title": "UI Designer", "category": "design_uxui", "seniority": "mid", "loc": "Warszawa", "salary": (10000, 14000), "work_mode": "hybrid"},
            {"title": "Brand Designer", "category": "design_brand", "seniority": "specialist", "loc": "Warszawa", "salary": (11000, 16000), "work_mode": "hybrid"},
            {"title": "Motion Designer", "category": "design_motion", "seniority": "specialist", "loc": "Remote (PL)", "salary": (12000, 17000), "work_mode": "remote"},
            {"title": "Senior Copywriter", "category": "marketing_copywriting", "seniority": "senior", "loc": "Warszawa", "salary": (11000, 16000), "work_mode": "hybrid"},
            {"title": "Performance Marketing Specialist", "category": "marketing_performance", "seniority": "specialist", "loc": "Warszawa", "salary": (10000, 14000), "work_mode": "hybrid"},
            {"title": "SEO Specialist", "category": "marketing_seo_sem", "seniority": "specialist", "loc": "Remote (PL)", "salary": (9000, 13000), "work_mode": "remote"},
            {"title": "Social Media Manager", "category": "marketing_social_media", "seniority": "specialist", "loc": "Warszawa", "salary": (8500, 12000), "work_mode": "hybrid"},
        ],
    },
    # ── 9. EuroBank Capital (EN)
    {
        "name": "EuroBank Capital",
        "slug": "eurobank-capital",
        "lang": "en",
        "verified": True,
        "blurb": "Mid-market commercial bank serving corporate clients across CEE. HQ in Warsaw, regional offices in Prague and Bratislava.",
        "jobs": [
            {"title": "Financial Analyst", "category": "fin_analyst", "seniority": "specialist", "loc": "Warszawa", "salary": (13000, 18000), "work_mode": "hybrid"},
            {"title": "Senior Accountant", "category": "fin_accountant", "seniority": "senior_specialist", "loc": "Warszawa", "salary": (12000, 17000), "work_mode": "hybrid"},
            {"title": "Risk Manager", "category": "fin_risk", "seniority": "manager", "loc": "Warszawa", "salary": (18000, 25000), "work_mode": "hybrid"},
            {"title": "Compliance Officer", "category": "fin_aml_compliance", "seniority": "specialist", "loc": "Warszawa", "salary": (14000, 19000), "work_mode": "hybrid"},
            {"title": "Treasury Specialist", "category": "fin_treasury", "seniority": "specialist", "loc": "Warszawa", "salary": (12000, 17000), "work_mode": "hybrid"},
            {"title": "Investment Banker Associate", "category": "fin_banking_investment", "seniority": "specialist", "loc": "Warszawa", "salary": (18000, 28000), "work_mode": "office"},
            {"title": "Corporate Banker", "category": "fin_banking_corporate", "seniority": "senior_specialist", "loc": "Warszawa", "salary": (15000, 22000), "work_mode": "hybrid"},
            {"title": "Tax Specialist", "category": "fin_tax", "seniority": "specialist", "loc": "Warszawa", "salary": (11000, 16000), "work_mode": "hybrid"},
        ],
    },
    # ── 10. PolEx Logistics (PL)
    {
        "name": "PolEx Logistics Sp. z o.o.",
        "slug": "polex-logistics",
        "lang": "pl",
        "verified": True,
        "blurb": "Międzynarodowa firma transportowo-spedycyjna z flotą 180 zestawów. Specjalizacja: trasy DE/NL/BE/PL.",
        "jobs": [
            {"title": "Kierowca C+E międzynarodowy", "category": "log_driver_heavy", "loc": "Łódź", "salary": (8500, 13000), "quals": ["driving_ce"]},
            {"title": "Kierowca C krajowy", "category": "log_driver_heavy", "loc": "Łódź", "salary": (6500, 9500), "quals": ["driving_c"]},
            {"title": "Magazynier (wózki UDT)", "category": "log_warehouse_op", "loc": "Łódź", "salary": (5500, 7500), "shift": "two_shift", "quals": ["forklift_udt"]},
            {"title": "Spedytor międzynarodowy", "category": "log_freight_forwarder", "seniority": "specialist", "loc": "Łódź", "salary": (8000, 12000), "work_mode": "hybrid"},
            {"title": "Kierownik magazynu", "category": "log_warehouse_manager", "seniority": "manager", "loc": "Łódź", "salary": (11000, 15000)},
            {"title": "Koordynator logistyki", "category": "log_coordinator", "seniority": "coordinator", "loc": "Łódź", "salary": (8500, 12000), "work_mode": "hybrid"},
            {"title": "Kurier", "category": "log_courier", "loc": "Warszawa", "salary": (4500, 6500), "quals": ["driving_b"]},
        ],
    },
    # ── 11. MedicaPlus Clinic Network (EN)
    {
        "name": "MedicaPlus Clinic Network",
        "slug": "medicaplus",
        "lang": "en",
        "verified": True,
        "blurb": "Premium private healthcare network with 14 clinics across Poland. Modern equipment, English-speaking staff.",
        "jobs": [
            {"title": "Dentist (Warsaw)", "category": "hc_dentist", "seniority": "attending", "loc": "Warszawa", "salary": (15000, 25000), "quals": ["medical_license"]},
            {"title": "Dental Hygienist", "category": "hc_dental_hygienist", "loc": "Warszawa", "salary": (6500, 9000)},
            {"title": "Physiotherapist", "category": "hc_physiotherapist", "seniority": "specialist", "loc": "Kraków", "salary": (7000, 10000)},
            {"title": "General Practitioner", "category": "hc_physician_gp", "seniority": "attending", "loc": "Warszawa", "salary": (16000, 26000), "quals": ["medical_license"]},
            {"title": "Pharmacist", "category": "hc_pharmacist", "loc": "Warszawa", "salary": (8500, 12000), "quals": ["pharmacy_license"]},
            {"title": "Registered Nurse", "category": "hc_nurse_registered", "loc": "Wrocław", "salary": (7000, 9500), "shift": "two_shift", "quals": ["first_aid"]},
            {"title": "Clinic Manager", "category": "hc_physician_gp", "seniority": "manager", "loc": "Kraków", "salary": (14000, 20000)},
        ],
    },
    # ── 12. BuildPro Construction (EN)
    {
        "name": "BuildPro Construction Sp. z o.o.",
        "slug": "buildpro",
        "lang": "en",
        "verified": True,
        "blurb": "Commercial and residential construction firm. Active sites in Warsaw, Kraków, Wrocław and Gdańsk.",
        "jobs": [
            {"title": "Construction Site Foreman", "category": "con_foreman", "seniority": "foreman", "loc": "Warszawa", "salary": (9000, 13000), "quals": ["bhp", "construction_license"]},
            {"title": "Construction Manager", "category": "con_manager", "seniority": "manager", "loc": "Kraków", "salary": (15000, 22000), "quals": ["construction_license"]},
            {"title": "Site Engineer", "category": "con_architect_assistant", "seniority": "specialist", "loc": "Wrocław", "salary": (9000, 13000)},
            {"title": "Electrician", "category": "con_electrician", "loc": "Warszawa", "salary": (7000, 10000), "quals": ["sep_g1", "construction_license"]},
            {"title": "Plumber", "category": "con_plumber", "loc": "Gdańsk", "salary": (6500, 9500), "quals": ["bhp"]},
            {"title": "Carpenter", "category": "con_carpenter", "loc": "Kraków", "salary": (6500, 9000), "quals": ["bhp"]},
            {"title": "Mason / Bricklayer", "category": "con_mason", "loc": "Wrocław", "salary": (6000, 8500), "quals": ["bhp"]},
            {"title": "HVAC Technician", "category": "con_hvac", "loc": "Warszawa", "salary": (7500, 10500), "quals": ["bhp"]},
        ],
    },
    # ── 13. TaxLab Doradztwo Podatkowe (PL)
    {
        "name": "TaxLab Doradztwo Podatkowe",
        "slug": "taxlab",
        "lang": "pl",
        "verified": True,
        "blurb": "Kancelaria doradztwa podatkowego obsługująca średnich i dużych podatników. 35 doradców, biura w Warszawie i Krakowie.",
        "jobs": [
            {"title": "Doradca podatkowy", "category": "fin_tax", "seniority": "senior_specialist", "loc": "Warszawa", "salary": (15000, 22000), "work_mode": "hybrid"},
            {"title": "Aplikant adwokacki", "category": "legal_paralegal", "seniority": "specialist", "loc": "Kraków", "salary": (8000, 12000), "work_mode": "hybrid"},
            {"title": "Księgowy/-a", "category": "fin_accountant", "seniority": "specialist", "loc": "Warszawa", "salary": (9500, 13500), "work_mode": "hybrid"},
            {"title": "Specjalista ds. cen transferowych", "category": "fin_tax", "seniority": "senior_specialist", "loc": "Warszawa", "salary": (14000, 19000), "work_mode": "hybrid"},
            {"title": "Audytor wewnętrzny", "category": "fin_audit", "seniority": "specialist", "loc": "Warszawa", "salary": (12000, 17000), "work_mode": "hybrid"},
        ],
    },
    # ── 14. Akademia Językowa Lingua (PL)
    {
        "name": "Akademia Językowa Lingua",
        "slug": "lingua",
        "lang": "pl",
        "verified": False,
        "blurb": "Sieć szkół językowych z 6 oddziałami w Polsce. Specjalizujemy się w kursach dla młodzieży i firm.",
        "jobs": [
            {"title": "Lektor języka angielskiego", "category": "edu_language_tutor", "loc": "Warszawa", "salary": (4500, 7500), "quals": ["language_cert"]},
            {"title": "Lektor języka niemieckiego", "category": "edu_language_tutor", "loc": "Kraków", "salary": (4500, 7500), "quals": ["language_cert"]},
            {"title": "Lektor języka hiszpańskiego", "category": "edu_language_tutor", "loc": "Wrocław", "salary": (4500, 7500), "quals": ["language_cert"]},
            {"title": "Metodyk", "category": "edu_vocational_trainer", "seniority": "specialist", "loc": "Warszawa", "salary": (8000, 11000)},
            {"title": "Koordynator szkoły", "category": "edu_school_counselor", "seniority": "coordinator", "loc": "Poznań", "salary": (6500, 9000)},
            {"title": "Recepcjonista szkoły", "category": "cs_receptionist", "loc": "Warszawa", "salary": (4500, 6000)},
        ],
    },
    # ── 15. CleanPro Services (EN)
    {
        "name": "CleanPro Services",
        "slug": "cleanpro",
        "lang": "en",
        "verified": True,
        "blurb": "B2B cleaning services for office buildings, retail and industrial sites. Active in 8 Polish cities.",
        "jobs": [
            {"title": "Residential Cleaner", "category": "cln_residential_cleaner", "loc": "Warszawa", "salary": (4200, 5500)},
            {"title": "Commercial Cleaner (Warsaw)", "category": "cln_commercial_cleaner", "loc": "Warszawa", "salary": (4500, 6000), "shift": "two_shift"},
            {"title": "Janitor", "category": "cln_janitor", "loc": "Kraków", "salary": (4200, 5500)},
            {"title": "Window Cleaner (heights)", "category": "cln_window_cleaner", "loc": "Warszawa", "salary": (5500, 7500), "quals": ["bhp"]},
            {"title": "Cleaning Supervisor", "category": "cln_commercial_cleaner", "seniority": "team_leader", "loc": "Wrocław", "salary": (5500, 7500)},
        ],
    },
    # ── 16. AutoNova Garage Network (PL)
    {
        "name": "AutoNova Garage Network",
        "slug": "autonova",
        "lang": "pl",
        "verified": True,
        "blurb": "Sieć 12 niezależnych warsztatów samochodowych z autoryzacją serwisową kilku marek europejskich.",
        "jobs": [
            {"title": "Mechanik samochodowy", "category": "auto_mechanic", "loc": "Warszawa", "salary": (6000, 9000), "quals": ["bhp"]},
            {"title": "Elektromechanik samochodowy", "category": "auto_electrician", "loc": "Kraków", "salary": (6500, 9500), "quals": ["sep_g1"]},
            {"title": "Blacharz samochodowy", "category": "auto_body_repair", "loc": "Warszawa", "salary": (6000, 8800)},
            {"title": "Lakiernik samochodowy", "category": "auto_painter", "loc": "Wrocław", "salary": (5800, 8500)},
            {"title": "Doradca serwisowy", "category": "auto_service_advisor", "seniority": "specialist", "loc": "Warszawa", "salary": (7000, 10000)},
            {"title": "Wulkanizator", "category": "auto_tire_tech", "loc": "Łódź", "salary": (4800, 6500)},
        ],
    },
    # ── 17. Bezpieczeństwo24 Ochrona (PL)
    {
        "name": "Bezpieczeństwo24 Ochrona",
        "slug": "bezpieczenstwo24",
        "lang": "pl",
        "verified": True,
        "blurb": "Agencja ochrony zatrudniająca licencjonowanych pracowników w ochronie obiektowej i konwojowej. 600 osób załogi.",
        "jobs": [
            {"title": "Pracownik ochrony (obiekt biurowy)", "category": "sec_security_guard", "loc": "Warszawa", "salary": (4800, 6500), "shift": "three_shift", "quals": ["security_license", "first_aid"]},
            {"title": "Pracownik ochrony (centrum handlowe)", "category": "sec_security_guard", "loc": "Kraków", "salary": (4500, 6200), "shift": "three_shift", "quals": ["security_license"]},
            {"title": "Konwojent", "category": "sec_cash_in_transit", "loc": "Warszawa", "salary": (6500, 9000), "quals": ["security_license", "driving_b"]},
            {"title": "Dowódca zmiany", "category": "sec_security_guard", "seniority": "team_leader", "loc": "Wrocław", "salary": (6000, 8500), "shift": "three_shift", "quals": ["security_license"]},
        ],
    },
    # ── 18. Boutique Beauty Spa (EN)
    {
        "name": "Boutique Beauty Spa",
        "slug": "boutique-spa",
        "lang": "en",
        "verified": False,
        "blurb": "High-end beauty & wellness spa in central Warsaw. Focus on natural treatments and personalized care.",
        "jobs": [
            {"title": "Senior Beautician", "category": "bty_beautician", "loc": "Warszawa", "salary": (5500, 8500), "quals": ["health_card"]},
            {"title": "Massage Therapist", "category": "bty_massage_therapist", "loc": "Warszawa", "salary": (5000, 8000), "quals": ["health_card"]},
            {"title": "Nail Technician", "category": "bty_nail_technician", "loc": "Warszawa", "salary": (4500, 7000), "quals": ["health_card"]},
            {"title": "Makeup Artist", "category": "bty_makeup_artist", "loc": "Warszawa", "salary": (5000, 7500), "quals": ["health_card"]},
            {"title": "Spa Receptionist", "category": "cs_receptionist", "loc": "Warszawa", "salary": (4500, 6000)},
            {"title": "Spa Manager", "category": "cln_property_manager", "seniority": "manager", "loc": "Warszawa", "salary": (9000, 13000)},
        ],
    },
    # ── 19. NextEra Robotics (EN)
    {
        "name": "NextEra Robotics",
        "slug": "nextera-robotics",
        "lang": "en",
        "verified": True,
        "blurb": "Industrial automation and robotics R&D company serving European manufacturing clients. Strong patent portfolio.",
        "jobs": [
            {"title": "Senior Automation Engineer", "category": "eng_automation_robotics", "seniority": "senior", "loc": "Poznań", "salary": (15000, 22000), "work_mode": "hybrid"},
            {"title": "Robotics Engineer", "category": "eng_automation_robotics", "seniority": "mid", "loc": "Poznań", "salary": (12000, 17000), "work_mode": "hybrid"},
            {"title": "Industrial Electrician", "category": "mfg_industrial_electrician", "loc": "Poznań", "salary": (7000, 10000), "quals": ["sep_g1", "sep_g2"]},
            {"title": "R&D Engineer", "category": "sci_research_scientist", "seniority": "senior", "loc": "Poznań", "salary": (16000, 23000), "work_mode": "hybrid"},
            {"title": "Quality Engineer", "category": "eng_quality", "seniority": "specialist", "loc": "Poznań", "salary": (11000, 15000), "work_mode": "hybrid"},
            {"title": "PLC Programmer", "category": "it_embedded", "seniority": "mid", "loc": "Poznań", "salary": (13000, 18000), "work_mode": "hybrid", "techs": ["Siemens TIA", "Allen-Bradley", "Ladder Logic"]},
        ],
    },
    # ── 20. Okrąglak Retail (PL)
    {
        "name": "Okrąglak Retail Sp. z o.o.",
        "slug": "okraglak-retail",
        "lang": "pl",
        "verified": True,
        "blurb": "Sieć 65 sklepów odzieżowych z polską modą damską. HQ w Łodzi, sklepy w całej Polsce.",
        "jobs": [
            {"title": "Kasjer/-ka (Warszawa)", "category": "ret_cashier", "loc": "Warszawa", "salary": (4200, 5500), "shift": "two_shift"},
            {"title": "Sprzedawca / Doradca klienta", "category": "ret_sales_associate", "loc": "Wrocław", "salary": (4500, 6000)},
            {"title": "Kierownik sklepu", "category": "ret_store_manager", "seniority": "manager", "loc": "Kraków", "salary": (7500, 10500)},
            {"title": "Visual Merchandiser", "category": "ret_visual_merchandiser", "seniority": "specialist", "loc": "Łódź", "salary": (7500, 10000)},
            {"title": "Pracownik magazynu sklepowego", "category": "ret_stockroom", "loc": "Łódź", "salary": (4500, 6200)},
            {"title": "Senior Buyer", "category": "ret_buyer_merchandiser", "seniority": "senior_specialist", "loc": "Łódź", "salary": (12000, 17000), "work_mode": "hybrid"},
        ],
    },

    # ──────────────────────────────────────────────────────────────────
    # HR AGENCIES — recruit for client companies, mixed industries
    # ──────────────────────────────────────────────────────────────────

    # ── 21. Randall & Partners Talent (EN)
    {
        "name": "Randall & Partners Talent",
        "slug": "randall-partners",
        "lang": "en",
        "verified": True,
        "is_agency": True,
        "blurb": "Senior-level executive search firm working with European tech and finance companies. Confidential mandates.",
        "jobs": [
            {"title": "CFO for FinTech scale-up", "category": "fin_cfo", "seniority": "executive", "loc": "Warszawa", "salary": (40000, 70000), "work_mode": "hybrid"},
            {"title": "Head of Marketing — DACH region", "category": "marketing_manager", "seniority": "director", "loc": "Berlin", "salary": (30000, 50000), "work_mode": "hybrid"},
            {"title": "VP of Engineering", "category": "it_tech_pm", "seniority": "director", "loc": "Remote (EU)", "salary": (35000, 60000), "work_mode": "remote"},
            {"title": "Country Manager Poland (FMCG)", "category": "ops_manager", "seniority": "director", "loc": "Warszawa", "salary": (28000, 45000)},
            {"title": "Head of People", "category": "hr_manager", "seniority": "director", "loc": "Warszawa", "salary": (22000, 35000), "work_mode": "hybrid"},
            {"title": "Chief Data Officer", "category": "it_data_scientist", "seniority": "executive", "loc": "Remote (EU)", "salary": (35000, 55000), "work_mode": "remote"},
            {"title": "Plant Director (Manufacturing)", "category": "mfg_plant_manager", "seniority": "director", "loc": "Gliwice", "salary": (28000, 42000)},
        ],
    },
    # ── 22. Personalia HR Solutions (PL)
    {
        "name": "Personalia HR Solutions",
        "slug": "personalia",
        "lang": "pl",
        "verified": True,
        "is_agency": True,
        "blurb": "Polska agencja rekrutacyjna specjalizująca się w stałych umowach dla średniego managementu w sektorze FMCG i przemyśle.",
        "jobs": [
            {"title": "Account Manager dla branży FMCG", "category": "sales_account_manager", "seniority": "specialist", "loc": "Warszawa", "salary": (10000, 14000)},
            {"title": "Junior Księgowa/-y", "category": "fin_accountant", "seniority": "junior", "loc": "Kraków", "salary": (5500, 7500), "work_mode": "hybrid"},
            {"title": "Specjalista ds. kadr i płac", "category": "hr_payroll_admin", "seniority": "specialist", "loc": "Wrocław", "salary": (7500, 10500), "work_mode": "hybrid"},
            {"title": "Trener wewnętrzny (sieć retail)", "category": "edu_vocational_trainer", "seniority": "specialist", "loc": "Warszawa", "salary": (8000, 11000)},
            {"title": "Recruiter IT (kontrakt)", "category": "hr_recruiter", "seniority": "specialist", "loc": "Remote (PL)", "salary": (9000, 13000), "work_mode": "remote"},
            {"title": "Kierownik produkcji (FMCG)", "category": "mfg_manager", "seniority": "manager", "loc": "Poznań", "salary": (13000, 18000)},
            {"title": "Brand Manager", "category": "marketing_brand", "seniority": "specialist", "loc": "Warszawa", "salary": (11000, 16000), "work_mode": "hybrid"},
            {"title": "Specjalista ds. sprzedaży B2B", "category": "sales_bizdev", "seniority": "specialist", "loc": "Łódź", "salary": (9000, 13000)},
        ],
    },
    # ── 23. HireForce Recruitment (EN)
    {
        "name": "HireForce Recruitment",
        "slug": "hireforce",
        "lang": "en",
        "verified": False,
        "is_agency": True,
        "blurb": "Specialist IT recruitment agency placing engineers across Europe. Permanent and contract roles.",
        "jobs": [
            {"title": "Senior Java Developer for FinTech", "category": "it_backend", "seniority": "senior", "loc": "Remote (EU)", "salary": (20000, 28000), "work_mode": "remote", "techs": ["Java", "Spring Boot", "Kafka", "AWS"]},
            {"title": "DevOps Engineer for HealthTech", "category": "it_devops", "seniority": "senior", "loc": "Remote (EU)", "salary": (19000, 27000), "work_mode": "remote", "techs": ["Kubernetes", "AWS", "Terraform", "GitOps"]},
            {"title": "Mobile Developer iOS — gaming", "category": "it_mobile", "seniority": "senior", "loc": "Remote (EU)", "salary": (18000, 25000), "work_mode": "remote", "techs": ["Swift", "Metal", "GameKit"]},
            {"title": "Frontend Lead — e-commerce", "category": "it_frontend", "seniority": "lead", "loc": "Warszawa", "salary": (22000, 30000), "work_mode": "hybrid", "techs": ["React", "Next.js", "TypeScript", "GraphQL"]},
            {"title": "Cloud Architect (AWS)", "category": "it_cloud_architect", "seniority": "expert", "loc": "Remote (EU)", "salary": (25000, 35000), "work_mode": "remote", "techs": ["AWS", "Terraform", "Multi-region"], "quals": ["aws_cert"]},
            {"title": "Cybersecurity Engineer", "category": "it_cybersecurity", "seniority": "senior", "loc": "Remote (PL)", "salary": (18000, 25000), "work_mode": "remote", "quals": ["cissp"]},
            {"title": "Data Scientist (e-commerce)", "category": "it_data_scientist", "seniority": "senior", "loc": "Remote (EU)", "salary": (18000, 26000), "work_mode": "remote", "techs": ["Python", "PyTorch", "BigQuery"]},
            {"title": "QA Automation Lead", "category": "it_qa_automation", "seniority": "lead", "loc": "Warszawa", "salary": (16000, 22000), "work_mode": "hybrid", "techs": ["Playwright", "TypeScript", "K6"]},
            {"title": "Tech Lead — SaaS platform", "category": "it_solutions_architect", "seniority": "lead", "loc": "Remote (EU)", "salary": (24000, 33000), "work_mode": "remote"},
            {"title": "Junior Java Developer", "category": "it_backend", "seniority": "junior", "loc": "Warszawa", "salary": (7000, 10000), "work_mode": "hybrid", "techs": ["Java", "Spring Boot"]},
        ],
    },
    # ── 24. GlobalStaff Polska (PL)
    {
        "name": "GlobalStaff Polska",
        "slug": "globalstaff",
        "lang": "pl",
        "verified": True,
        "is_agency": True,
        "blurb": "Agencja pracy tymczasowej i stałej. Specjalizacja: produkcja, magazyny, logistyka. Obsługujemy klientów w całej Polsce.",
        "jobs": [
            {"title": "Operator linii produkcyjnej (Wrocław)", "category": "mfg_operator", "loc": "Wrocław", "salary": (4800, 6500), "shift": "three_shift", "quals": ["health_card"]},
            {"title": "Pracownik magazynu (Łódź)", "category": "log_warehouse_op", "loc": "Łódź", "salary": (4500, 6200), "shift": "two_shift", "quals": ["forklift_udt"]},
            {"title": "Kierowca kat. C+E (DE/PL)", "category": "log_driver_heavy", "loc": "Poznań", "salary": (8000, 12000), "quals": ["driving_ce"]},
            {"title": "Pakowacz (1 zmiana)", "category": "mfg_assembly", "loc": "Łódź", "salary": (4500, 5800), "shift": "one_shift"},
            {"title": "Operator wózka widłowego", "category": "log_warehouse_op", "loc": "Wrocław", "salary": (5000, 7000), "shift": "two_shift", "quals": ["forklift_udt"]},
            {"title": "Pracownik produkcji (różne kierunki)", "category": "mfg_operator", "loc": "Gdańsk", "salary": (4500, 6200), "shift": "three_shift"},
            {"title": "Spawacz MAG (Wrocław)", "category": "mfg_welder", "loc": "Wrocław", "salary": (6000, 9000)},
            {"title": "Brygadzista — produkcja", "category": "mfg_team_leader", "seniority": "team_leader", "loc": "Poznań", "salary": (7500, 10500), "shift": "three_shift"},
        ],
    },
    # ── 25. WorkBridge Executive Search (EN)
    {
        "name": "WorkBridge Executive Search",
        "slug": "workbridge",
        "lang": "en",
        "verified": True,
        "is_agency": True,
        "blurb": "Executive search firm with European reach. Focus on C-suite and VP-level placements in B2B SaaS, manufacturing and life sciences.",
        "jobs": [
            {"title": "Managing Director — Logistics", "category": "ops_manager", "seniority": "executive", "loc": "Warszawa", "salary": (35000, 55000)},
            {"title": "Chief Operating Officer", "category": "ops_manager", "seniority": "executive", "loc": "Wrocław", "salary": (40000, 65000)},
            {"title": "Head of Engineering", "category": "eng_industrial", "seniority": "director", "loc": "Katowice", "salary": (25000, 38000)},
            {"title": "VP Sales — Eastern Europe", "category": "sales_manager", "seniority": "director", "loc": "Warszawa", "salary": (28000, 45000), "work_mode": "hybrid"},
            {"title": "Director of Operations (Pharma)", "category": "ops_manager", "seniority": "director", "loc": "Kraków", "salary": (26000, 40000)},
            {"title": "Chief Information Security Officer", "category": "it_cybersecurity", "seniority": "executive", "loc": "Warszawa", "salary": (30000, 48000), "work_mode": "hybrid", "quals": ["cissp"]},
        ],
    },
]


# ──────────────────────────────────────────────────────────────────────
# Form-template archetypes — each Job gets matched to one based on its category
# ──────────────────────────────────────────────────────────────────────

# Field shape: (label, field_type, required, options-as-list-or-None)
# `options` is stored as dict {"choices": [...]} in DB (matches existing UI expectations).

def _opts(*choices: str) -> list[str]:
    """Form-field `options` value. Stored as a plain list of strings — matches
    Pydantic schema `FormFieldRead.options: list[str] | None` and the
    DynamicField renderer on the frontend."""
    return list(choices)


FORM_TEMPLATE_DEFS: dict[str, dict[str, Any]] = {
    # ── IT / engineering (EN)
    "it_tech": {
        "name": "Technical IT application",
        "lang": "en",
        "fields": [
            ("GitHub or portfolio URL", "text", False, None),
            ("LinkedIn URL", "text", False, None),
            ("Years of commercial experience", "number", True, None),
            ("Available from", "date", False, None),
            ("Notice period (weeks)", "number", False, None),
            ("Preferred work mode", "select", False, _opts("Remote", "Hybrid", "On-site")),
            ("Why this role?", "textarea", False, None),
            ("English level", "select", True, _opts("B1", "B2", "C1", "C2 / native")),
        ],
    },
    # ── Production / blue-collar (PL)
    "production_pl": {
        "name": "Aplikacja na stanowisko produkcyjne",
        "lang": "pl",
        "fields": [
            ("Lata doświadczenia w produkcji", "number", True, None),
            ("Uprawnienia (wybierz jakie posiadasz)", "multiselect", False,
             _opts("Wózki widłowe UDT", "SEP G1", "SEP G2", "SEP G3", "Książeczka sanepidowska", "HACCP", "Szkolenie BHP")),
            ("Preferowana zmiana", "select", False, _opts("Tylko dzienna", "Tylko nocna", "Dowolna")),
            ("Mogę natychmiast rozpocząć pracę", "checkbox", False, None),
            ("Brak przeciwwskazań medycznych do pracy fizycznej", "checkbox", True, None),
        ],
    },
    # ── Driver (PL)
    "driver_pl": {
        "name": "Aplikacja kierowca",
        "lang": "pl",
        "fields": [
            ("Posiadane kategorie prawa jazdy", "multiselect", True,
             _opts("B", "C", "C+E", "D", "T")),
            ("Karta kierowcy ważna", "checkbox", False, None),
            ("Lata doświadczenia w prowadzeniu", "number", True, None),
            ("Preferowane trasy", "select", False, _opts("Krajowe", "Międzynarodowe", "Mieszane")),
            ("Aktualne badania psychotechniczne", "checkbox", False, None),
            ("Znane języki obce", "multiselect", False, _opts("Angielski", "Niemiecki", "Rosyjski", "Inne")),
            ("Dyspozycyjność wyjazdowa", "select", False, _opts("Cały tydzień", "5/2", "Tylko weekendy")),
        ],
    },
    # ── Medical (PL)
    "medical_pl": {
        "name": "Aplikacja na stanowisko medyczne",
        "lang": "pl",
        "fields": [
            ("Numer PWZ", "text", True, None),
            ("Specjalizacja / kierunek", "text", False, None),
            ("Lata praktyki", "number", True, None),
            ("Dyspozycyjność", "select", True, _opts("Pełny etat", "3/4 etatu", "1/2 etatu", "Zlecenie / kontrakt")),
            ("Możliwość pracy zmianowej (24h)", "checkbox", False, None),
            ("Możliwość pracy w weekendy", "checkbox", False, None),
            ("Dodatkowe certyfikaty", "textarea", False, None),
        ],
    },
    # ── Medical (EN, private clinics)
    "medical_en": {
        "name": "Medical role application",
        "lang": "en",
        "fields": [
            ("Medical license / PWZ number", "text", True, None),
            ("Specialization", "text", False, None),
            ("Years in practice", "number", True, None),
            ("Available employment type", "select", True, _opts("Full-time", "Part-time 75%", "Part-time 50%", "Contract")),
            ("Open to shift work", "checkbox", False, None),
            ("English level", "select", True, _opts("B2", "C1", "C2 / native")),
        ],
    },
    # ── Hospitality (EN)
    "hospitality_en": {
        "name": "Hospitality application",
        "lang": "en",
        "fields": [
            ("Years of experience", "number", True, None),
            ("Languages spoken", "multiselect", True, _opts("English", "Polish", "German", "French", "Spanish", "Russian", "Italian")),
            ("Available shifts", "multiselect", True, _opts("Morning", "Evening", "Night", "Weekend")),
            ("Food handler / sanepid certificate", "checkbox", False, None),
            ("HACCP training completed", "checkbox", False, None),
            ("Why work with us?", "textarea", False, None),
        ],
    },
    # ── Sales (PL/EN — language picked dynamically by company)
    "sales_pl": {
        "name": "Aplikacja na stanowisko handlowe",
        "lang": "pl",
        "fields": [
            ("Lata doświadczenia w sprzedaży", "number", True, None),
            ("Branże obsługiwanych dotąd klientów", "textarea", False, None),
            ("Posiadam prawo jazdy kat. B", "checkbox", False, None),
            ("Akceptowany % delegacji w miesiącu", "number", False, None),
            ("LinkedIn URL", "text", False, None),
            ("Znane języki obce", "multiselect", False, _opts("Angielski", "Niemiecki", "Hiszpański", "Francuski", "Inne")),
        ],
    },
    "sales_en": {
        "name": "Sales role application",
        "lang": "en",
        "fields": [
            ("Years of sales experience", "number", True, None),
            ("Industries of past clients", "textarea", False, None),
            ("Driver's license B", "checkbox", False, None),
            ("Acceptable travel %", "number", False, None),
            ("LinkedIn URL", "text", False, None),
            ("Languages", "multiselect", False, _opts("English", "Polish", "German", "Spanish", "French", "Other")),
        ],
    },
    # ── Finance / banking (EN — corporate language)
    "finance_en": {
        "name": "Finance role application",
        "lang": "en",
        "fields": [
            ("Years of experience", "number", True, None),
            ("Highest education", "select", True, _opts("Bachelor", "Master", "MBA", "PhD")),
            ("Professional certifications", "multiselect", False, _opts("ACCA", "CFA", "CIA", "CIMA", "CPA", "FRM", "None")),
            ("Notice period (weeks)", "number", False, None),
            ("English level", "select", True, _opts("B2", "C1", "C2 / native")),
            ("LinkedIn URL", "text", False, None),
        ],
    },
    "finance_pl": {
        "name": "Aplikacja finansowa",
        "lang": "pl",
        "fields": [
            ("Lata doświadczenia", "number", True, None),
            ("Wykształcenie", "select", True, _opts("Licencjat", "Magister", "MBA", "Doktor")),
            ("Posiadane uprawnienia", "multiselect", False, _opts("Biegły rewident", "Doradca podatkowy", "ACCA", "CFA", "Aplikant", "Brak")),
            ("Znajomość systemów", "multiselect", False, _opts("SAP", "Comarch ERP", "enova365", "Symfonia", "Płatnik", "Excel zaawansowany")),
            ("LinkedIn URL", "text", False, None),
        ],
    },
    # ── Teacher (PL)
    "teacher_pl": {
        "name": "Aplikacja lektor / nauczyciel",
        "lang": "pl",
        "fields": [
            ("Język / przedmiot nauczania", "text", True, None),
            ("Posiadane certyfikaty", "multiselect", False, _opts("CAE", "CPE", "DELF/DALF", "Goethe-Zertifikat", "DELE", "TKT", "CELTA", "Inne")),
            ("Kwalifikacje pedagogiczne", "checkbox", False, None),
            ("Lata doświadczenia w nauczaniu", "number", True, None),
            ("Preferowani uczniowie", "multiselect", False, _opts("Przedszkole", "Dzieci", "Młodzież", "Dorośli", "Firmy / B2B")),
            ("Dostępność tygodniowo (godziny)", "number", False, None),
        ],
    },
    # ── Construction (EN/PL)
    "construction_en": {
        "name": "Construction role application",
        "lang": "en",
        "fields": [
            ("Years on construction sites", "number", True, None),
            ("Construction license / Uprawnienia budowlane", "checkbox", False, None),
            ("Health & safety training (BHP)", "checkbox", True, None),
            ("Electrical SEP G1/G2/G3", "multiselect", False, _opts("SEP G1", "SEP G2", "SEP G3", "None")),
            ("Driving license", "multiselect", False, _opts("B", "C", "C+E", "None")),
            ("Willing to travel for site work", "checkbox", False, None),
        ],
    },
    # ── Design / creative
    "design_en": {
        "name": "Design / creative application",
        "lang": "en",
        "fields": [
            ("Portfolio URL", "text", True, None),
            ("Behance / Dribbble", "text", False, None),
            ("LinkedIn URL", "text", False, None),
            ("Years of experience", "number", True, None),
            ("Software you use daily", "multiselect", False,
             _opts("Figma", "Sketch", "Adobe XD", "Photoshop", "Illustrator", "After Effects", "Premiere Pro", "Cinema 4D", "Blender")),
            ("Open to remote work", "checkbox", False, None),
        ],
    },
    # ── Legal (PL)
    "legal_pl": {
        "name": "Aplikacja prawna",
        "lang": "pl",
        "fields": [
            ("Uprawnienia / status zawodowy", "select", True,
             _opts("Adwokat", "Radca prawny", "Aplikant adwokacki", "Aplikant radcowski", "Doradca podatkowy", "Notariusz", "Brak / w trakcie")),
            ("Specjalizacja / dziedzina prawa", "text", False, None),
            ("Lata doświadczenia w zawodzie", "number", True, None),
            ("Języki obce", "multiselect", False, _opts("Angielski", "Niemiecki", "Francuski", "Włoski", "Hiszpański")),
            ("LinkedIn URL", "text", False, None),
        ],
    },
    # ── Beauty / wellness (EN)
    "beauty_en": {
        "name": "Beauty / wellness role application",
        "lang": "en",
        "fields": [
            ("Years of experience", "number", True, None),
            ("Certifications", "textarea", False, None),
            ("Food handler / health certificate", "checkbox", False, None),
            ("Available shifts", "multiselect", False, _opts("Morning", "Evening", "Weekend")),
            ("Languages", "multiselect", False, _opts("English", "Polish", "German", "Russian", "Other")),
        ],
    },
    # ── Security (PL)
    "security_pl": {
        "name": "Aplikacja na stanowisko ochrony",
        "lang": "pl",
        "fields": [
            ("Posiadana licencja pracownika ochrony", "checkbox", True, None),
            ("Lata doświadczenia w ochronie", "number", True, None),
            ("Posiadane prawo jazdy", "multiselect", False, _opts("B", "C", "Brak")),
            ("Kurs Kwalifikowanego Pracownika Ochrony Fizycznej (KPOF)", "checkbox", False, None),
            ("Pierwsza pomoc — szkolenie aktualne", "checkbox", False, None),
            ("Preferowana lokalizacja obiektu", "text", False, None),
        ],
    },
    # ── Automotive (PL)
    "automotive_pl": {
        "name": "Aplikacja motoryzacyjna",
        "lang": "pl",
        "fields": [
            ("Lata doświadczenia w warsztacie", "number", True, None),
            ("Marki samochodów na których pracowałeś", "textarea", False, None),
            ("Uprawnienia SEP G1", "checkbox", False, None),
            ("Prawo jazdy kat. B", "checkbox", True, None),
            ("Diagnostyka komputerowa — doświadczenie", "select", False,
             _opts("Brak", "Podstawowe", "Średnio-zaawansowane", "Eksperckie")),
        ],
    },
    # ── Executive search (EN, HR agency)
    "executive_search_en": {
        "name": "Executive search application",
        "lang": "en",
        "fields": [
            ("Current role and company", "text", True, None),
            ("LinkedIn URL", "text", True, None),
            ("Years in leadership roles", "number", True, None),
            ("Compensation expectations (annual)", "textarea", False, None),
            ("Open to relocation", "checkbox", False, None),
            ("Languages", "multiselect", False, _opts("English", "Polish", "German", "French", "Other")),
            ("Notice period (weeks)", "number", False, None),
        ],
    },
    # ── Logistics / warehouse (PL)
    "logistics_pl": {
        "name": "Aplikacja logistyka / magazyn",
        "lang": "pl",
        "fields": [
            ("Uprawnienia UDT na wózki widłowe", "checkbox", False, None),
            ("Lata pracy w logistyce / magazynie", "number", True, None),
            ("Znajomość systemów WMS", "multiselect", False, _opts("SAP EWM", "Manhattan", "Comarch WMS", "Logito", "Brak / inny")),
            ("Preferowana zmiana", "select", False, _opts("Tylko dzienna", "Tylko nocna", "Dowolna")),
            ("Język angielski na poziomie komunikatywnym", "checkbox", False, None),
        ],
    },
    # ── Retail (PL)
    "retail_pl": {
        "name": "Aplikacja sprzedaż detaliczna",
        "lang": "pl",
        "fields": [
            ("Doświadczenie w sprzedaży detalicznej (lata)", "number", True, None),
            ("Dostępność godzinowa tygodniowo", "number", False, None),
            ("Możliwość pracy w weekendy", "checkbox", False, None),
            ("Dodatkowe języki", "multiselect", False, _opts("Angielski", "Niemiecki", "Ukraiński", "Inny")),
            ("Książeczka sanepidowska", "checkbox", False, None),
        ],
    },
    # ── Generic fallback
    "general_pl": {
        "name": "Aplikacja ogólna",
        "lang": "pl",
        "fields": [
            ("LinkedIn URL", "text", False, None),
            ("Dlaczego chcesz pracować właśnie u nas?", "textarea", False, None),
            ("Okres wypowiedzenia (tygodnie)", "number", False, None),
            ("Oczekiwane wynagrodzenie", "text", False, None),
        ],
    },
    "general_en": {
        "name": "General application",
        "lang": "en",
        "fields": [
            ("LinkedIn URL", "text", False, None),
            ("Why do you want to work with us?", "textarea", False, None),
            ("Notice period (weeks)", "number", False, None),
            ("Salary expectations", "text", False, None),
        ],
    },
}


def pick_template_for_job(category: str, company_lang: str, is_agency: bool) -> str:
    """Map a job category code to the best matching template archetype."""
    if not category:
        return "general_en" if company_lang == "en" else "general_pl"

    # IT-family
    if category.startswith("it_"):
        return "it_tech"
    # Design / creative
    if category.startswith("design_") or category.startswith("marketing_") and "copy" not in category:
        if "marketing_" in category:
            # Marketing roles use sales archetype EN, design/creative use design_en
            return "sales_en" if company_lang == "en" else "sales_pl"
        return "design_en"
    # Marketing
    if category.startswith("marketing_"):
        return "sales_en" if company_lang == "en" else "sales_pl"
    # Sales
    if category.startswith("sales_"):
        return "sales_en" if company_lang == "en" else "sales_pl"
    # Drivers
    if category in ("log_driver_heavy", "log_driver_light", "log_driver_bus", "log_courier"):
        return "driver_pl"
    # Warehouse / logistics
    if category.startswith("log_"):
        return "logistics_pl"
    # Manufacturing / production
    if category.startswith("mfg_"):
        return "production_pl"
    # Construction
    if category.startswith("con_"):
        return "construction_en" if company_lang == "en" else "production_pl"
    # Healthcare
    if category.startswith("hc_"):
        return "medical_en" if company_lang == "en" else "medical_pl"
    # Education
    if category.startswith("edu_"):
        return "teacher_pl"
    # Hospitality
    if category.startswith("hsp_"):
        return "hospitality_en"
    # Retail
    if category.startswith("ret_"):
        return "retail_pl"
    # Beauty
    if category.startswith("bty_"):
        return "beauty_en"
    # Security
    if category.startswith("sec_"):
        return "security_pl"
    # Automotive
    if category.startswith("auto_"):
        return "automotive_pl"
    # Finance
    if category.startswith("fin_"):
        # Executive-level finance roles in agencies → executive search
        if is_agency and category == "fin_cfo":
            return "executive_search_en"
        return "finance_en" if company_lang == "en" else "finance_pl"
    # Legal
    if category.startswith("legal_"):
        return "legal_pl"
    # Engineering (non-IT)
    if category.startswith("eng_"):
        return "construction_en"
    # Cleaning, energy, agriculture, etc.
    return "general_en" if company_lang == "en" else "general_pl"


# ──────────────────────────────────────────────────────────────────────
# Job rendering — fill in sensible defaults per language
# ──────────────────────────────────────────────────────────────────────

def render_job_content(company: dict, job: dict) -> dict[str, Any]:
    lang = company["lang"]
    title = job["title"]
    is_agency = company.get("is_agency", False)

    if lang == "pl":
        role_summary = (
            f"{company['name']} poszukuje osoby na stanowisko {title.lower()}. "
            f"{company['blurb']}"
            if not is_agency
            else f"Rekrutujemy dla naszego klienta na stanowisko {title.lower()}. Stała umowa, atrakcyjne warunki."
        )
        responsibilities_items = [
            "Wykonywanie obowiązków zgodnie z procedurami stanowiska",
            "Współpraca z zespołem i przełożonym",
            "Dbanie o standardy jakości i bezpieczeństwa",
            "Raportowanie postępów prac",
        ]
        must_haves_items = [
            "Doświadczenie na podobnym stanowisku",
            "Zaangażowanie i samodzielność",
            "Komunikatywność",
        ]
        benefits_items = [
            "Stabilne zatrudnienie i terminowe wypłaty",
            "Prywatna opieka medyczna",
            "Karta sportowa",
            "Premie kwartalne uzależnione od wyników",
            "Możliwość rozwoju i awansu",
        ]
        process_items = [
            "Analiza CV",
            "Rozmowa telefoniczna z rekruterem",
            "Rozmowa z managerem zespołu",
            "Oferta zatrudnienia",
        ]
    else:
        role_summary = (
            f"{company['name']} is hiring a {title}. {company['blurb']}"
            if not is_agency
            else f"On behalf of our client, we are looking for a {title}. Permanent contract, attractive package."
        )
        responsibilities_items = [
            "Deliver on the responsibilities of the role end-to-end",
            "Collaborate closely with team members and stakeholders",
            "Maintain quality and security standards",
            "Report progress and outcomes regularly",
        ]
        must_haves_items = [
            "Proven experience in a similar role",
            "Strong communication skills",
            "Self-directed work ethic",
            "Fluent English",
        ]
        benefits_items = [
            "Competitive salary and regular reviews",
            "Private medical care",
            "Sport card",
            "Annual learning budget",
            "Growth and promotion opportunities",
        ]
        process_items = [
            "CV review",
            "Intro call with recruiter",
            "Technical / managerial interview",
            "Offer",
        ]

    return {
        "role_summary": role_summary,
        "responsibilities": ul(responsibilities_items),
        "must_haves": ul(must_haves_items),
        "benefits": ul(benefits_items),
        "hiring_process": ol(process_items),
        "team_context": company["blurb"],
    }


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

async def main(reset: bool = False) -> None:
    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        if reset:
            print("⚠ Wiping previous job-board seed (companies tagged '(seeded)' or '(demo)')…")
            await db.execute(text("""
                DELETE FROM jobs WHERE company_id IN (
                    SELECT id FROM companies
                    WHERE name LIKE '%(seeded)%' OR name LIKE '%(demo)%'
                )
            """))
            await db.execute(text("""
                DELETE FROM users WHERE company_id IN (
                    SELECT id FROM companies
                    WHERE name LIKE '%(seeded)%' OR name LIKE '%(demo)%'
                )
            """))
            await db.execute(text("""
                DELETE FROM companies WHERE name LIKE '%(seeded)%' OR name LIKE '%(demo)%'
            """))
            await db.commit()

        password_hash = hash_password(DEMO_PASSWORD)
        total_jobs = 0
        total_templates = 0

        for company_def in COMPANIES:
            display_name = f"{company_def['name']} (demo)"
            company = Company(name=display_name, is_verified=company_def["verified"])
            db.add(company)
            await db.flush()

            owner_email = f"{company_def['slug']}@demo.wakanta.pl"
            owner = User(
                company_id=company.id,
                email=owner_email,
                password_hash=password_hash,
                role="owner",
                is_verified=True,
                language=company_def["lang"],
            )
            db.add(owner)
            await db.flush()

            # ── Pre-create the form templates this company actually needs.
            # For each unique archetype referenced by its jobs, build one
            # FormTemplate + FormFields. Cache by archetype name so multiple
            # jobs that need the same template re-use one record.
            is_agency = company_def.get("is_agency", False)
            needed_archetypes: set[str] = set()
            for j in company_def["jobs"]:
                needed_archetypes.add(pick_template_for_job(j["category"], company_def["lang"], is_agency))

            template_cache: dict[str, FormTemplate] = {}
            for archetype in needed_archetypes:
                tpl_def = FORM_TEMPLATE_DEFS[archetype]
                tpl = FormTemplate(company_id=company.id, name=tpl_def["name"])
                db.add(tpl)
                await db.flush()
                for idx, (label, ftype, required, options) in enumerate(tpl_def["fields"]):
                    field = FormField(
                        template_id=tpl.id,
                        label=label,
                        field_type=ftype,
                        required=required,
                        options=options,
                        order_index=idx,
                    )
                    db.add(field)
                template_cache[archetype] = tpl
                total_templates += 1
            await db.flush()

            print(f"  ✓ {display_name} — {len(company_def['jobs'])} ofert, {len(template_cache)} szablonów")

            for job_def in company_def["jobs"]:
                content = render_job_content(company_def, job_def)
                salary_min, salary_max = job_def["salary"]
                salary_period = job_def.get("salary_period", "month")

                # Render tech_stack HTML from list
                tech_html = None
                if job_def.get("techs"):
                    tech_html = ul(job_def["techs"])

                # Slug
                location_part = (job_def.get("loc") or "").lower()[:8]
                slug = f"{slugify(job_def['title'])}-{location_part}-{uuid.uuid4().hex[:6]}"

                # Pick contract default by language convention
                default_contract = "b2b" if (company_def["lang"] == "en" and ("Engineer" in job_def["title"] or "Developer" in job_def["title"])) else "employment"

                job = Job(
                    company_id=company.id,
                    title=job_def["title"],
                    slug=slug,
                    location=job_def.get("loc"),
                    status="open",
                    category=job_def["category"],
                    seniority=job_def.get("seniority"),
                    work_mode=job_def.get("work_mode", "office"),
                    contract_type=job_def.get("contract_type", default_contract),
                    employment_size=job_def.get("employment_size", "full"),
                    shift_system=job_def.get("shift"),
                    required_qualifications=job_def.get("quals", []),
                    salary_min=salary_min,
                    salary_max=salary_max,
                    salary_currency="PLN",
                    salary_period=salary_period,
                    tech_stack=tech_html,
                    role_summary=content["role_summary"],
                    responsibilities=content["responsibilities"],
                    must_haves=content["must_haves"],
                    benefits=content["benefits"],
                    hiring_process=content["hiring_process"],
                    team_context=content["team_context"],
                )
                # Random recent creation date for "newest" sort to be meaningful
                job.created_at = datetime.now(UTC) - timedelta(hours=random.randint(0, 720))
                db.add(job)
                await db.flush()
                total_jobs += 1

                # Link the job to its matching form template (preserves the
                # company-scoped variant we just created above).
                archetype = pick_template_for_job(job_def["category"], company_def["lang"], is_agency)
                tpl = template_cache[archetype]
                db.add(JobFormTemplate(job_id=job.id, template_id=tpl.id))

            await db.flush()

        await db.commit()
        print(f"\n✓ Done. {len(COMPANIES)} firm, {total_jobs} ofert, {total_templates} szablonów formularzy.")
        print(f"  Login dla każdej firmy: <slug>@demo.wakanta.pl  /  hasło: {DEMO_PASSWORD}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Wipe previous seed first")
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset))
