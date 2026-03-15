# ATS Platform — Backend API

Production-ready FastAPI backend for a multi-tenant SaaS Applicant Tracking System (ATS).

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| Language | Python 3.12 |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Auth | JWT (access + refresh tokens) + Google OAuth |
| Email | SMTP + Jinja2 HTML templates |
| Rate limiting | slowapi |
| File storage | Local filesystem |

---

## Project Structure

```
backend/
├── app/
│   ├── core/
│   │   ├── config.py          # Pydantic settings
│   │   ├── database.py        # SQLAlchemy engine + session
│   │   ├── dependencies.py    # FastAPI dependency injection
│   │   └── security.py        # JWT, bcrypt, OAuth
│   ├── models/
│   │   └── base.py            # Base ORM model (UUID + timestamps)
│   ├── modules/
│   │   ├── auth/              # Login, signup, refresh, Google OAuth
│   │   ├── companies/         # Company management
│   │   ├── users/             # User management
│   │   ├── jobs/              # Job postings
│   │   ├── forms/             # Dynamic form templates
│   │   ├── applications/      # Candidate applications + scoring
│   │   ├── pipeline/          # Recruitment pipeline stages
│   │   ├── notes/             # Recruiter notes
│   │   ├── tags/              # Candidate tagging
│   │   └── audit/             # Audit logging
│   ├── services/
│   │   ├── mailer.py          # SMTP email service
│   │   └── file_storage.py    # CV file upload service
│   └── main.py                # FastAPI app factory
├── alembic/                   # Database migrations
├── seeds/
│   └── seed.py                # Database seeder
├── templates/email/           # HTML email templates
├── tests/                     # pytest test suite
├── uploads/cv/                # Uploaded CV files
├── .env.example               # Environment variable template
├── alembic.ini                # Alembic configuration
└── requirements.txt           # Python dependencies
```

---

## Getting Started

### Prerequisites

- Python 3.12
- PostgreSQL (or Docker)
- Git

### 1. Clone and set up virtual environment

```bash
git clone <repo-url>
cd backend

python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the database

Using Docker (recommended):

```bash
docker run --name ats_db \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=ats_db \
  -p 5432:5432 \
  -d postgres:16
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```env
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/ats_db
JWT_SECRET=your-secret-key-here
SECRET_KEY=your-app-secret-here
FRONTEND_URL=http://localhost:3000
APP_ENV=development
DEBUG=true
```

### 5. Run database migrations

```bash
alembic upgrade head
```

### 6. Seed the database (optional)

```bash
# Seed all data
python seeds/seed.py

# Seed only pipeline stages
python seeds/seed.py --stages

# Wipe and re-seed everything
python seeds/seed.py --fresh
```

Default seeded accounts:

| Email | Password | Role | Company |
|---|---|---|---|
| owner@acme.com | Password123! | owner | Acme Technologies |
| recruiter@acme.com | Password123! | recruiter | Acme Technologies |
| manager@acme.com | Password123! | manager | Acme Technologies |
| owner@novasoft.com | Password123! | owner | NovaSoft |

### 7. Start the server

```bash
uvicorn app.main:app --reload
```

API available at: **http://localhost:8000**
Swagger docs: **http://localhost:8000/docs**
ReDoc: **http://localhost:8000/redoc**

---

## API Overview

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/signup-company` | Register new company + owner |
| POST | `/api/v1/auth/login` | Login with email/password |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| POST | `/api/v1/auth/logout` | Logout and clear cookies |
| GET | `/api/v1/auth/me` | Get current user |
| GET | `/api/v1/auth/google` | Google OAuth URL |
| GET | `/api/v1/auth/google/callback` | Google OAuth callback |

### Jobs

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/jobs` | List all jobs |
| POST | `/api/v1/jobs` | Create job |
| GET | `/api/v1/jobs/{id}` | Get job details |
| PATCH | `/api/v1/jobs/{id}` | Update job |
| DELETE | `/api/v1/jobs/{id}` | Delete job |

### Applications

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/applications/apply/{job_id}` | Public: submit application |
| GET | `/api/v1/applications/track/{token}` | Public: track application |
| GET | `/api/v1/applications` | List applications |
| GET | `/api/v1/applications/{id}` | Get application detail |
| POST | `/api/v1/applications/{id}/score` | Score a candidate |

### Pipeline

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/pipeline` | List pipeline stages |
| PATCH | `/api/v1/pipeline/applications/{id}/stage` | Move candidate to stage |

### Notes & Tags

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/notes/applications/{id}/notes` | Add note |
| GET | `/api/v1/notes/applications/{id}/notes` | List notes |
| POST | `/api/v1/tags` | Create tag |
| POST | `/api/v1/tags/applications/{id}/tags` | Assign tag |
| GET | `/api/v1/tags/applications/{id}/tags` | Get application tags |

---

## Authentication Flow

The API uses **httpOnly cookies** for authentication:

1. Client calls `POST /auth/login`
2. Server sets `access_token` cookie (15 min) and `refresh_token` cookie (30 days)
3. All subsequent requests send cookies automatically
4. When access token expires, client calls `POST /auth/refresh`
5. Server rotates both tokens

---

## Multi-tenancy

Every resource is scoped to a `company_id`. Users can only access data belonging to their own company. This is enforced via the `get_current_company` dependency injected into all protected routes.

---

## Running Tests

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=app --cov-report=html
```

---

## Database Migrations

Create a new migration after changing models:

```bash
alembic revision --autogenerate -m "description of change"
alembic upgrade head
```

Rollback one migration:

```bash
alembic downgrade -1
```

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | required |
| `JWT_SECRET` | Secret key for JWT signing | required |
| `SECRET_KEY` | App secret key | required |
| `APP_ENV` | Environment: development/production | `development` |
| `DEBUG` | Enable debug mode | `false` |
| `FRONTEND_URL` | Frontend URL for CORS | `http://localhost:3000` |
| `SMTP_HOST` | SMTP server host | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP server port | `587` |
| `SMTP_USER` | SMTP username | — |
| `SMTP_PASSWORD` | SMTP password | — |
| `UPLOAD_DIR` | File upload directory | `uploads` |
| `MAX_UPLOAD_SIZE_MB` | Max CV file size in MB | `10` |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | — |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | — |

---

## License

MIT