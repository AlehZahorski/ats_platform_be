# TalentMatch - Backend API

## Jak uruchomić projekt

Wykonaj poniższe kroki w podanej kolejności. Każdy krok wymaga osobnego terminala (backend i frontend działają równolegle).

---

### Krok 1 — Aktywuj wirtualne środowisko

```bash
# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

> Jeśli venv nie istnieje, utwórz go najpierw: `python -m venv venv`, a następnie zainstaluj zależności: `pip install -r requirements.txt`

---

### Krok 2 — Uruchom bazę danych (Docker)

```bash
docker run --name ats_db \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=ats_db \
  -p 5432:5432 \
  -d postgres:16
```

Jeśli kontener już istnieje (kolejne uruchomienia):

```bash
docker start ats_db
```

Sprawdź czy baza działa:

```bash
docker ps
```

> **Pierwsze uruchomienie** — po starcie bazy wykonaj migracje:
> ```bash
> alembic upgrade head
> ```

---

### Krok 3 — Uruchom backend (terminal 1)

Upewnij się, że venv jest aktywny, a następnie:

```bash
uvicorn app.main:app --reload
```

Backend dostępny pod: **http://localhost:8000**
Swagger (dokumentacja API): **http://localhost:8000/docs**

---

### Krok 4 — Uruchom frontend (terminal 2)

```bash
cd ../frontend
npm run dev -- --turbo
```

Aplikacja dostępna pod: **http://localhost:3000**

---

### Domyślne konta (po seed)

Opcjonalnie załaduj dane testowe:

```bash
python seeds/seed.py
```

| Email | Hasło | Rola |
|---|---|---|
| owner@acme.com | Password123! | owner |
| recruiter@acme.com | Password123! | recruiter |
| manager@acme.com | Password123! | manager |
| owner@novasoft.com | Password123! | owner |

---

## Konfiguracja środowiska

Plik `.env` powinien znajdować się w katalogu `backend/`. Skopiuj przykład jeśli nie masz:

```bash
cp .env.example .env
```

Minimalna konfiguracja działająca lokalnie jest już ustawiona w `.env.example` — nie wymaga zmian do developmentu.

---

## Migracje bazy danych

```bash
# Zastosuj wszystkie migracje
alembic upgrade head

# Nowa migracja po zmianie modeli
alembic revision --autogenerate -m "opis zmiany"

# Cofnij ostatnią migrację
alembic downgrade -1
```

---

## Tech Stack

| Warstwa | Technologia |
|---|---|
| Framework | FastAPI |
| Język | Python 3.12 |
| Baza danych | PostgreSQL |
| ORM | SQLAlchemy 2.0 (async) |
| Migracje | Alembic |
| Auth | JWT (access + refresh tokens) + Google OAuth |
| Email | SMTP + Jinja2 |
| Rate limiting | slowapi |

---

## Testy

```bash
pytest
pytest --cov=app --cov-report=html
```
