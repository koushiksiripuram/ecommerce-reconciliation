# E-commerce Financial Reconciliation Platform

Foundation for a financial reconciliation platform built for a D2C home textiles
business. The application shell, the PostgreSQL data model and
authentication/RBAC are in place — no file uploads, AI features, or
reconciliation logic yet.

## Tech stack

| Layer     | Technology                              |
| --------- | --------------------------------------- |
| Backend   | Python, FastAPI, Uvicorn                |
| Frontend  | React, TypeScript, Vite                 |
| Database  | PostgreSQL                              |
| ORM       | SQLAlchemy 2.x                          |
| Migrations| Alembic                                 |

## Directory structure

```
ecommerce-reconciliation/
├── .gitignore                  # Ignores .env files, virtualenvs, node_modules, build output
├── README.md
├── backend/
│   ├── .env.example            # Template for backend environment variables
│   ├── requirements.txt        # Runtime dependencies
│   ├── requirements-dev.txt    # Test dependencies (pytest, httpx)
│   ├── pytest.ini              # Pytest configuration
│   ├── alembic.ini             # Alembic configuration (DB URL supplied at runtime)
│   ├── alembic/
│   │   ├── env.py              # Migration environment; reads settings + Base.metadata
│   │   ├── script.py.mako      # Template for generated migration files
│   │   └── versions/
│   │       ├── 6e9f95855415_create_initial_schema.py
│   │       └── 533d946dd507_add_password_hash_to_users.py
│   ├── app/
│   │   ├── main.py             # FastAPI application entry point (app + CORS + router)
│   │   ├── cli.py              # `python -m app.cli create-user` (only way to add users)
│   │   ├── api/
│   │   │   ├── router.py       # Aggregates all route modules under the API prefix
│   │   │   ├── deps.py         # get_current_user + require_roles() RBAC dependencies
│   │   │   └── routes/
│   │   │       ├── health.py   # GET /api/health
│   │   │       └── auth.py     # POST /api/auth/login, GET /api/auth/me, POST /api/auth/logout
│   │   ├── core/
│   │   │   ├── config.py       # Environment-driven settings + database URL + JWT/cookie config
│   │   │   ├── security.py     # Argon2 hashing + JWT create/decode helpers
│   │   │   └── roles.py        # RoleName enum shared by deps and the CLI
│   │   ├── db/
│   │   │   ├── base.py         # DeclarativeBase, constraint naming, timestamp mixin
│   │   │   ├── session.py      # Engine, sessionmaker, get_db dependency
│   │   │   └── types.py        # portable_enum() column type helper
│   │   ├── schemas/
│   │   │   └── auth.py         # LoginRequest, UserRead, RoleRead (never exposes hashes)
│   │   └── models/
│   │       ├── __init__.py     # Imports every model so metadata is complete
│   │       ├── enums.py        # Shared status/type enumerations
│   │       ├── user.py         # Role, User (incl. password_hash)
│   │       ├── order.py        # Order
│   │       ├── imports.py      # UploadedFile, ImportBatch, RawImportedRecord
│   │       ├── settlement.py   # SettlementRecord
│   │       └── reconciliation.py  # ReconciliationResult
│   └── tests/
│       ├── conftest.py         # Settings/env isolation fixtures
│       ├── test_config.py      # Configuration tests
│       ├── test_health.py      # API tests
│       ├── test_security.py    # Password hashing + JWT primitives
│       ├── test_auth.py        # Login/logout/me + RBAC restrictions
│       ├── test_models.py      # Model structure + ORM behaviour tests
│       └── test_migrations.py  # Migration runs and matches the models
└── frontend/
    ├── .env.example            # Template for frontend environment variables
    ├── index.html              # Vite HTML entry point
    ├── vite.config.ts          # Vite config + /api dev proxy to the backend
    ├── package.json
    └── src/
        ├── main.tsx            # React entry point
        ├── App.tsx             # Shell: gates on auth state, holds active navigation state
        ├── index.css           # Global styles + design tokens
        ├── api/
        │   └── client.ts       # Backend API client (health, login, me, logout)
        ├── auth/
        │   └── AuthContext.tsx # Session state: loading/authenticated/unauthenticated
        ├── components/
        │   ├── Layout.tsx      # Sidebar + main content layout
        │   └── Sidebar.tsx     # Primary navigation + user block + sign out
        ├── config/
        │   ├── navigation.ts   # Sidebar navigation definitions
        │   └── roles.ts        # Role name → display label
        └── pages/
            ├── Login.tsx       # Login screen
            ├── Overview.tsx    # Overview page with placeholder content
            └── Placeholder.tsx # Placeholder for not-yet-built sections
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- A PostgreSQL 14+ database. A **hosted** instance is expected — no local
  installation is needed for development, and the API starts without one.
  Only `alembic upgrade` and any runtime query actually connect.

## Backend setup

From the `backend/` directory:

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Windows (PowerShell)
# source .venv/bin/activate       # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your local environment file
#    Copy .env.example to .env and adjust the values.
copy .env.example .env            # Windows
# cp .env.example .env            # macOS / Linux

# 4. Start the API (from the backend/ directory, so app/ is importable)
uvicorn app.main:app --reload --port 8000
```

The API is then available at `http://localhost:8000`, with interactive docs at
`http://localhost:8000/docs`.

### Environment variables (`backend/.env.example`)

| Variable            | Description                                          | Default            |
| ------------------- | ---------------------------------------------------- | ------------------ |
| `APP_NAME`          | Application title shown in the OpenAPI docs           | — |
| `ENVIRONMENT`       | Deployment environment label                          | `development`      |
| `DEBUG`             | Enables FastAPI debug mode                            | `true`             |
| `API_PREFIX`        | Prefix applied to all API routes                      | `/api`             |
| `CORS_ORIGINS`      | JSON array of allowed frontend origins                | `["http://localhost:5173"]` |
| `DATABASE_URL`      | Full SQLAlchemy URL; **takes precedence when set**    | — (unset)          |
| `POSTGRES_HOST`     | PostgreSQL host (used when `DATABASE_URL` is unset)   | `localhost`        |
| `POSTGRES_PORT`     | PostgreSQL port                                       | `5432`             |
| `POSTGRES_USER`     | PostgreSQL user                                       | `postgres`         |
| `POSTGRES_PASSWORD` | PostgreSQL password                                   | `postgres`         |
| `POSTGRES_DB`       | PostgreSQL database name                              | `reconciliation`   |
| `JWT_SECRET_KEY`    | HMAC secret used to sign access tokens. **Required** outside development | dev placeholder (development only) |
| `JWT_ALGORITHM`     | JWT signing algorithm                                 | `HS256`            |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime in minutes         | `60`               |
| `AUTH_COOKIE_NAME`  | Name of the HttpOnly cookie holding the token          | `access_token`     |
| `AUTH_COOKIE_SECURE`| Restricts the cookie to HTTPS                          | `false`            |
| `AUTH_COOKIE_SAMESITE` | Cookie `SameSite` policy (`lax`/`strict`/`none`)    | `lax`              |

> `CORS_ORIGINS` must be valid JSON, e.g. `["http://localhost:5173","https://app.example.com"]`.

The database connection has two mutually exclusive options:

- **Option A — `DATABASE_URL` (recommended for hosted PostgreSQL).** Set a single
  full connection string, which is exactly what most managed providers hand you:

  ```
  DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
  ```

- **Option B — discrete `POSTGRES_*` variables.** The URL is assembled from the
  individual parts. Useful for local or containerised development.

`DATABASE_URL` wins whenever it is present. No credentials are committed to the
repository — `.env` is git-ignored and only `.env.example` is tracked.

### Database schema

The initial migration creates eight tables:

| Table                   | Purpose                                                          |
| ----------------------- | ---------------------------------------------------------------- |
| `roles`                 | Roles (`finance_executive`, `co_founder`), seeded by the migration |
| `users`                 | Users linked to a role; each user has an active flag              |
| `orders`                | Marketplace orders with monetary breakdown per order              |
| `uploaded_files`        | Metadata for each uploaded source file                            |
| `import_batches`        | One processing run of an uploaded file (status, row counters)     |
| `raw_imported_records`  | Immutable raw rows as parsed, with validation errors              |
| `settlement_records`    | Settlement/payout lines, optionally linked to an order            |
| `reconciliation_results`| Outcome of comparing an order against a settlement record         |

Design notes:

- All monetary values use `NUMERIC(14, 2)` — never floating point.
- Every table has an integer primary key plus `created_at`/`updated_at`
  timestamps. `raw_imported_records` is append-only, so it only has `created_at`.
- A `MetaData` naming convention gives deterministic constraint names
  (`pk_*`, `fk_*`, `uq_*`, `ix_*`, `ck_*`), which keeps migrations stable.
- Enum-like columns are stored as `VARCHAR` with a `CHECK` constraint
  (`native_enum=False`) so the schema stays portable across databases.

### Database migrations (Alembic)

The initial migration `6e9f95855415_create_initial_schema.py` already exists in
`backend/alembic/versions/`. Apply it once your hosted database is reachable:

```bash
# From the backend/ directory, with the virtualenv active and .env populated:
alembic upgrade head          # create all tables + seed the roles

alembic current               # show the revision the database is on
alembic downgrade base        # drop everything (destructive)
```

The database URL is read from application settings (`DATABASE_URL` or the
`POSTGRES_*` variables), so `alembic.ini` contains no hardcoded URL. Model
metadata is registered through `app/models/__init__.py`, which `alembic/env.py`
imports — add any new model there so it is picked up by autogenerate.

To add a future migration:

```bash
alembic revision --autogenerate -m "describe the change"
```

> A hosted PostgreSQL database is not required to run the tests or start the
> API. Only `alembic upgrade` and runtime queries actually connect.

## Authentication & authorization (RBAC)

Authentication is **JWT-based** and delivered to browsers in an **HttpOnly
cookie**, so client-side JavaScript can never read the token.

| Endpoint              | Method | Description                                        |
| --------------------- | ------ | -------------------------------------------------- |
| `/api/auth/login`     | POST   | Verify credentials, set the auth cookie, return the user |
| `/api/auth/me`        | GET    | Return the authenticated user (requires a valid token) |
| `/api/auth/logout`    | POST   | Clear the auth cookie (204)                        |

Both roles seeded by the migration are supported: **`finance_executive`** and
**`co_founder`**. Role checks are applied with the `require_roles()` dependency
factory in `backend/app/api/deps.py`, e.g.:

```python
from fastapi import APIRouter, Depends
from app.api.deps import require_roles
from app.core.roles import RoleName

router = APIRouter()

@router.get("/founder-only")
def founder_only(_=Depends(require_roles(RoleName.CO_FOUNDER))):
    ...
```

`get_current_user` returns **401** (with `WWW-Authenticate: Bearer`) when the
token is missing, malformed, expired or belongs to a non-existent user, and
`require_roles` returns **403** when the user's role is not permitted.

### Creating users

There is **no public registration and no default credentials**. The only way to
create a user is the CLI command, which hashes the password with Argon2id before
inserting:

```bash
# From the backend/ directory, with the virtualenv active and .env populated.
# Prompts for the password (with confirmation) when --password is omitted.
python -m app.cli create-user \
  --email finance@example.com \
  --full-name "Finance Executive" \
  --role finance_executive
```

Passwords are never returned by any endpoint: the API response schema
(`UserRead`) exposes only `id`, `email`, `full_name`, `is_active` and `role`.

### Security decisions & token-storage limitations

- **Hashing:** Argon2id via `argon2-cffi` (a maintained library) — the current
  OWASP-recommended default, with a per-password random salt.
- **Token storage:** the access token is sent in an **HttpOnly** cookie rather
  than `localStorage`, so it is immune to XSS token theft. Because the cookie is
  attached automatically by the browser, the trade-off is exposure to **CSRF**;
  mitigations are `SameSite=Lax` by default and the fact that the API only
  accepts JSON `POST`s. A cross-site deployment must set
  `AUTH_COOKIE_SAMESITE=none` **and** `AUTH_COOKIE_SECURE=true` (i.e. serve over
  HTTPS), otherwise browsers will refuse to send the cookie.
- **Enumeration:** unknown email and wrong password return the **same** 401
  message, and an unknown email still runs a dummy Argon2 verify to equalise
  response time.
- **Secret handling:** `JWT_SECRET_KEY` is read from the environment only. The
  placeholder default is rejected at startup whenever `ENVIRONMENT` is not
  `development`/`local`/`test`. No credentials or secrets are committed.

## Testing

Tests run against in-memory SQLite, so no PostgreSQL instance is needed.

```bash
# From the backend/ directory, with the virtualenv active:
pip install -r requirements-dev.txt   # installs pytest + httpx on top of runtime deps
pytest                                # run the whole suite
pytest tests/test_models.py           # run a single module
```

Coverage includes configuration/URL assembly, the health endpoint, password
hashing and JWT primitives, login/logout/`me` behaviour (valid and invalid
credentials, missing/invalid/expired tokens, no credential leakage), RBAC
restrictions per role, model structure (keys, indexes, `NUMERIC(14, 2)` money
columns, timestamps, enums), ORM behaviour (relationships, server defaults,
cascades) and the Alembic migration (schema matches the models, roles are
seeded, constraints enforced).

## Frontend setup

From the `frontend/` directory:

```bash
# 1. Install dependencies
npm install

# 2. Create your local environment file (optional; defaults are provided)
copy .env.example .env            # Windows
# cp .env.example .env            # macOS / Linux

# 3. Start the dev server
npm run dev
```

The app is available at `http://localhost:5173`.

### Frontend ↔ backend connectivity

The Vite dev server proxies requests beginning with `/api` to
`http://localhost:8000` (see `frontend/vite.config.ts`), so no CORS
configuration is needed during development.

The API base URL is read from `VITE_API_BASE_URL` and defaults to `/api`. The
Overview page calls `GET /api/health` on load and displays the connection status.

All requests are sent with `credentials: 'include'` so the HttpOnly auth cookie
travels with them. On load, the app calls `GET /api/auth/me` to determine whether
a session already exists; until it resolves it shows a loading state, and an
unauthenticated result renders the login screen instead of the application shell.
The signed-in user's name and role are shown at the bottom of the sidebar, next
to a **Sign out** button that calls `POST /api/auth/logout`.

| Variable            | Description                                  | Default |
| ------------------- | -------------------------------------------- | ------- |
| `VITE_API_BASE_URL` | Base URL used for backend API calls          | `/api`  |

## Running both applications

Open two terminals:

```bash
# Terminal 1 — backend
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

Then open `http://localhost:5173`. You will be shown the login screen; sign in
with a user created via the CLI (see [Creating users](#creating-users)). After
signing in, the sidebar provides navigation for **Overview**, **Imports**,
**Reconciliation**, **Rate Cards**, **Returns**, and **Claims**; only Overview
has content at this stage.

### Verifying the setup

```bash
# Backend health check (direct)
curl http://localhost:8000/api/health
# -> {"status":"ok","service":"backend"}

# Backend health check (through the Vite dev proxy)
curl http://localhost:5173/api/health
# -> {"status":"ok","service":"backend"}
```

## Other useful commands

| Command                        | Location   | Purpose                          |
| ------------------------------ | ---------- | -------------------------------- |
| `npm run build`                | `frontend` | Type-check and production build  |
| `npm run preview`              | `frontend` | Preview the production build     |
| `npm run lint`                 | `frontend` | Run the linter                   |
| `alembic upgrade head`         | `backend`  | Apply pending migrations         |
| `alembic revision --autogenerate -m "..."` | `backend` | Generate a new migration |
| `python -m app.cli create-user ...` | `backend` | Create a user (hashes the password) |
| `pytest`                       | `backend`  | Run the test suite               |

## Scope

Implemented: the application shell, the PostgreSQL data model, and JWT
authentication with role-based access control.

Not yet implemented, by design: file uploads, import/reconciliation logic, and
AI features.
