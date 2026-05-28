# wakanta.pl — Backend (FastAPI)

> **Primary path for setting the project up is the root `README.md`.**
> The `docker compose up --build` workflow there boots Postgres, runs
> Alembic migrations on container start and serves both the API and the
> frontend. Use that unless you have a specific reason not to.
>
> This file documents the **secondary path** — running the FastAPI
> service directly on your host (no Docker for the API), which is the
> faster inner loop when you are iterating on Python code.

---

## Without Docker (host venv + Postgres in Docker)

### 1. Postgres

The simplest option is to run **only** Postgres in Docker:

```bash
docker compose up -d db
```

(`db` is the service name in the root `docker-compose.yml`.) If you
prefer a plain container:

```bash
docker run --name ats_db -d \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=ats_db \
  -p 5432:5432 \
  postgres:16
```

### 2. Python environment

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt
# Local / CI also need the test runner:
pip install -r requirements-dev.txt
```

### 3. Config

```bash
cp .env.example .env
```

`.env.example` is preconfigured for the local Postgres above. The only
secret you have to generate is `JWT_SECRET` — see the root README.

### 4. Migrations + seed

```bash
alembic upgrade head
python seeds/realistic_seed.py
```

### 5. Run the API

```bash
uvicorn app.main:app --reload
```

- API:  http://localhost:8000
- Docs: http://localhost:8000/docs

Demo accounts come from the seed and match the table in the root
`README.md` (password `demo1234`).

---

## Migrations cheat-sheet

```bash
alembic upgrade head                                    # apply all
alembic revision --autogenerate -m "what changed"       # create one
alembic downgrade -1                                    # roll back one
alembic history                                         # show graph
```

Models live under `app/modules/<feature>/models.py`. `alembic/env.py`
auto-discovers them via `pkgutil.walk_packages` so adding a new module
does not require editing the env file.

## Tests

```bash
pytest -q
pytest --cov=app --cov-report=html
```

The test suite currently runs against **SQLite in-memory** — see
`audit/audit_backend_code_2026_05_28_DONE.md` finding C1 for the
testcontainers migration plan. Some JSONB / Postgres-only paths are
therefore exercised only against a real DB.

## Tech stack

| Layer        | Choice                                            |
| ------------ | ------------------------------------------------- |
| Framework    | FastAPI 0.116                                     |
| Language     | Python 3.12                                       |
| Database     | PostgreSQL 16                                     |
| ORM          | SQLAlchemy 2.0 (async)                            |
| Migrations   | Alembic                                           |
| Auth         | JWT (access + refresh cookies) + Google OAuth     |
| Password hash| native `bcrypt` (rounds=12)                       |
| Email        | SMTP + Jinja2                                     |
| Rate limit   | `slowapi` (per-user when authenticated, per-IP otherwise) |
| LLM          | Anthropic SDK (async, prompt-cache, retries)      |

## Further reading

- `../README.md` — primary onboarding + Docker compose flow
- `../CONTRIBUTING.md` — branches, commits, PR checklist
- `../docs/operations.md` — runbook (deploy, rollback, common incidents)
- `../audit/` — completed audits and their `_DONE` implementation status
- `app/modules/<feature>/` — every module ships `router + service +
  repository + schemas + models`
