# E-commerce Financial Reconciliation Platform

Foundation for a financial reconciliation platform built for a D2C home textiles
business. The application shell and the PostgreSQL data model are in place — no
authentication, file uploads, AI features, or reconciliation logic yet.

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
│   │       └── 6e9f95855415_create_initial_schema.py
│   ├── app/
│   │   ├── main.py             # FastAPI application entry point (app + CORS + router)
│   │   ├── api/
│   │   │   ├── router.py       # Aggregates all route modules under the API prefix
│   │   │   └── routes/
│   │   │       └── health.py   # GET /api/health
│   │   ├── core/
│   │   │   └── config.py       # Environment-driven settings + database URL
│   │   ├── db/
│   │   │   ├── base.py         # DeclarativeBase, constraint naming, timestamp mixin
│   │   │   ├── session.py      # Engine, sessionmaker, get_db dependency
│   │   │   └── types.py        # portable_enum() column type helper
│   │   └── models/
│   │       ├── __init__.py     # Imports every model so metadata is complete
│   │       ├── enums.py        # Shared status/type enumerations
│   │       ├── user.py         # Role, User
│   │       ├── order.py        # Order
│   │       ├── imports.py      # UploadedFile, ImportBatch, RawImportedRecord
│   │       ├── settlement.py   # SettlementRecord
│   │       └── reconciliation.py  # ReconciliationResult
│   └── tests/
│       ├── conftest.py         # Settings/env isolation fixtures
│       ├── test_config.py      # Configuration tests
│       ├── test_health.py      # API tests
│       ├── test_models.py      # Model structure + ORM behaviour tests
│       └── test_migrations.py  # Migration runs and matches the models
└── frontend/
    ├── .env.example            # Template for frontend environment variables
    ├── index.html              # Vite HTML entry point
    ├── vite.config.ts          # Vite config + /api dev proxy to the backend
    ├── package.json
    └── src/
        ├── main.tsx            # React entry point
        ├── App.tsx             # Shell: holds active navigation state
        ├── index.css           # Global styles + design tokens
        ├── api/
        │   └── client.ts       # Backend API client (health request)
        ├── components/
        │   ├── Layout.tsx      # Sidebar + main content layout
        │   └── Sidebar.tsx     # Primary navigation
        ├── config/
        │   └── navigation.ts   # Sidebar navigation definitions
        └── pages/
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

## Testing

Tests run against in-memory SQLite, so no PostgreSQL instance is needed.

```bash
# From the backend/ directory, with the virtualenv active:
pip install -r requirements-dev.txt   # installs pytest + httpx on top of runtime deps
pytest                                # run the whole suite
pytest tests/test_models.py           # run a single module
```

Coverage includes configuration/URL assembly, the health endpoint, model
structure (keys, indexes, `NUMERIC(14, 2)` money columns, timestamps, enums),
ORM behaviour (relationships, server defaults, cascades) and the Alembic
migration (schema matches the models, roles are seeded, constraints enforced).

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

Then open `http://localhost:5173`. The sidebar provides navigation for
**Overview**, **Imports**, **Reconciliation**, **Rate Cards**, **Returns**, and
**Claims**; only Overview has content at this stage.

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
| `pytest`                       | `backend`  | Run the test suite               |

## Scope

Not yet implemented, by design: authentication, AI features, file uploads, and
reconciliation logic.
