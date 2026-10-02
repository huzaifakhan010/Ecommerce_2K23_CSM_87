# Custom Print-on-Demand Studio — Backend (Sprint 2: Catalog Data Foundation)

FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL. Sprint 1 decisions: `docs/SPRINT_1.md`.
Sprint 2 design, ERD, API reference and evidence: **`docs/SPRINT_2.md`**.

## Local setup

Requires Python 3.10+ and (for PostgreSQL) Docker, or any PostgreSQL 14+ server.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

docker compose up -d db              # PostgreSQL on localhost:5432 (local-dev credentials only)
cp .env.example .env                 # Windows: copy .env.example .env
# edit .env and set JWT_SECRET, e.g.:
python -c "import secrets; print(secrets.token_urlsafe(48))"

alembic upgrade head                 # create the schema
python -m scripts.seed               # reproducible demo data (idempotent)
uvicorn app.main:app --reload        # API on http://127.0.0.1:8000  (Swagger UI: /docs)
```

### Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@localhost:5432/printstudio` |
| `JWT_SECRET` | yes | Signing key for access tokens (>= 16 random characters). **Never commit it.** |
| `ACCESS_TOKEN_MINUTES` | no (60) | Token lifetime |
| `BCRYPT_ROUNDS` | no (12) | Password-hash cost |
| `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` | seed only | Admin created by `scripts.seed` (a dev default is used, with a warning, if the password is unset) |
| `TEST_DATABASE_URL` | tests only | Optional: run the test-suite on PostgreSQL instead of in-memory SQLite |

`.env` is git-ignored; only `.env.example` (no secrets) is committed.

## Tests

```bash
pytest -v                                        # in-memory SQLite, no services needed
TEST_DATABASE_URL=postgresql+psycopg://... pytest -v   # same suite on PostgreSQL (use an EMPTY test database!)
```

## Demo evidence

```bash
JWT_SECRET=demo-secret-0123456789 python -m scripts.demo     # PowerShell: $env:JWT_SECRET="demo-secret-0123456789"; python -m scripts.demo
```
Writes real request/response pairs (tokens redacted) to `DEMO_EVIDENCE.md`.

## Quick manual try-out

```bash
TOKEN=$(curl -s localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email":"admin@example.com","password":"<your SEED_ADMIN_PASSWORD>"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s localhost:8000/api/v1/admin/products -H "Authorization: Bearer $TOKEN"
```

## Layout

```
app/            models.py (tables+constraints) · schemas.py (validation) · services.py (business rules)
                routers/admin.py (protected catalog API) · routers/auth.py · deps.py · errors.py · security.py
alembic/        migrations (0001_catalog_foundation)
scripts/        seed.py (reproducible data) · demo.py (evidence generator)
tests/          model/constraint, validation, categories, variants/SKUs, authorization, auth, seed, migration tests
docs/           SPRINT_1.md · SPRINT_2.md
```
