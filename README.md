# E-commerce Financial Reconciliation Platform

Financial reconciliation platform built for a D2C home textiles business. It
ingests orders, marketplace settlements, COD remittances, freight invoices and
returns, maps each partner's own columns onto platform "canonical" fields, and
reconciles the money every order expected against the money actually received —
flagging short payments, unpaid orders, duplicate settlements and freight
overcharges.

Implemented end to end: the application shell, the PostgreSQL data model, JWT
authentication with role-based access control, the import pipeline (upload →
mapping → processing), the reconciliation engine with immutable run history, and
the React UI for both Imports and Reconciliation.

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
│   │       ├── 533d946dd507_add_password_hash_to_users.py
│   │       ├── a4f1c8b9d2e3_add_import_mapping_support.py
│   │       ├── b7c2e1f4a6d9_add_reconciliation_engine.py
│   │       └── c1d2e3f4a5b6_add_reconciliation_run_history.py
│   ├── app/
│   │   ├── main.py             # FastAPI application entry point (app + CORS + router)
│   │   ├── cli.py              # `python -m app.cli create-user` (only way to add users)
│   │   ├── api/
│   │   │   ├── router.py       # Aggregates all route modules under the API prefix
│   │   │   ├── deps.py         # get_current_user + require_roles() RBAC dependencies
│   │   │   └── routes/
│   │   │       ├── health.py         # GET /api/health
│   │   │       ├── auth.py           # login / me / logout
│   │   │       ├── imports.py        # upload, mapping, processing, records
│   │   │       └── reconciliation.py # run + results + summary + run history
│   │   ├── core/
│   │   │   ├── config.py       # Environment-driven settings + database URL + JWT/cookie config
│   │   │   ├── security.py     # Argon2 hashing + JWT create/decode helpers
│   │   │   └── roles.py        # RoleName enum shared by deps and the CLI
│   │   ├── db/
│   │   │   ├── base.py         # DeclarativeBase, constraint naming, timestamp mixin
│   │   │   ├── session.py      # Engine, sessionmaker, get_db dependency
│   │   │   └── types.py        # portable_enum() column type helper
│   │   ├── imports/            # The import pipeline (parsing → mapping → normalising)
│   │   │   ├── fields.py       # Canonical-field registry: names, kinds, aliases
│   │   │   ├── parser.py       # CSV/XLSX → headers + raw rows
│   │   │   ├── mapping.py      # Header → canonical-field suggestion engine
│   │   │   ├── normalizer.py   # Raw text → typed values (dates, amounts, weights)
│   │   │   ├── service.py      # Upload / mapping-approval / processing orchestration
│   │   │   └── errors.py       # ImportPipelineError hierarchy → HTTP statuses
│   │   ├── reconciliation/     # The matching engine
│   │   │   ├── service.py      # project → link → compare → record (+ run ledger)
│   │   │   └── freight.py      # Rate-card lookup for expected freight
│   │   ├── schemas/
│   │   │   ├── auth.py         # LoginRequest, UserRead, RoleRead (never exposes hashes)
│   │   │   ├── imports.py      # Batch / preview / mapping / record schemas
│   │   │   └── reconciliation.py  # Result / run / summary schemas
│   │   └── models/
│   │       ├── __init__.py     # Imports every model so metadata is complete
│   │       ├── enums.py        # Shared status/type enumerations
│   │       ├── user.py         # Role, User (incl. password_hash)
│   │       ├── order.py        # Order
│   │       ├── imports.py      # UploadedFile, ImportBatch, RawImportedRecord
│   │       ├── mappings.py     # ImportColumnMapping (saved per source + partner)
│   │       ├── settlement.py   # SettlementRecord
│   │       ├── freight.py      # FreightRateCard (configurable weight slabs)
│   │       └── reconciliation.py  # ReconciliationResult + ReconciliationRun
│   └── tests/
│       ├── conftest.py         # Settings/env isolation fixtures
│       ├── test_config.py      # Configuration tests
│       ├── test_health.py      # API tests
│       ├── test_security.py    # Password hashing + JWT primitives
│       ├── test_auth.py        # Login/logout/me + RBAC restrictions
│       ├── test_models.py      # Model structure + ORM behaviour tests
│       ├── test_migrations.py  # Migration runs and matches the models
│       ├── test_imports_parser.py      # CSV/XLSX parsing
│       ├── test_imports_mapping.py     # Mapping suggestion + saved configs
│       ├── test_imports_normalizer.py  # Date/amount/text normalisation
│       ├── test_imports_service.py     # End-to-end import pipeline
│       ├── test_imports_api.py         # Import endpoints + RBAC
│       ├── test_reconciliation_service.py  # Matching, partial payments, dupes
│       ├── test_reconciliation_api.py      # Reconciliation endpoints + RBAC
│       └── test_reconciliation_e2e.py      # Upload → process → run, end to end
└── frontend/
    ├── .env.example            # Template for frontend environment variables
    ├── index.html              # Vite HTML entry point
    ├── vite.config.ts          # Vite config + /api dev proxy to the backend
    ├── vitest.config.ts        # Vitest configuration (jsdom)
    ├── package.json
    └── src/
        ├── main.tsx            # React entry point
        ├── App.tsx             # Shell: gates on auth state, holds active navigation state
        ├── index.css           # Global styles + design tokens
        ├── api/
        │   ├── client.ts           # Shared fetch wrapper (auth cookie, error mapping)
        │   ├── imports.ts          # Typed import client
        │   └── reconciliation.ts   # Typed reconciliation client
        ├── auth/
        │   └── AuthContext.tsx # Session state: loading/authenticated/unauthenticated
        ├── components/
        │   ├── Layout.tsx      # Sidebar + main content layout
        │   └── Sidebar.tsx     # Primary navigation + user block + sign out
        ├── config/
        │   ├── navigation.ts   # Sidebar navigation definitions
        │   └── roles.ts        # Role name → label + canManage*() capability helpers
        ├── test/               # Vitest setup + shared fixtures
        └── pages/
            ├── Login.tsx       # Login screen
            ├── Overview.tsx    # Overview page
            ├── Placeholder.tsx # Placeholder for not-yet-built sections
            ├── Imports.tsx     # Imports workflow (upload → map → process → history)
            ├── imports/        # UploadForm, MappingEditor, PreviewTable, History, Detail
            └── reconciliation/ # Summary, ResultsTable, Runs, Detail + formatters
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

The migrations create eleven tables:

| Table                   | Purpose                                                          |
| ----------------------- | ---------------------------------------------------------------- |
| `roles`                 | Roles (`finance_executive`, `co_founder`), seeded by the migration |
| `users`                 | Users linked to a role; each user has an active flag              |
| `orders`                | Marketplace orders with monetary breakdown per order              |
| `uploaded_files`        | Metadata for each uploaded source file                            |
| `import_batches`        | One processing run of an uploaded file (status, row counters, mapping) |
| `raw_imported_records`  | Immutable raw rows as parsed, plus normalised values and errors   |
| `import_column_mappings`| Saved header→canonical mappings, reused per source + partner      |
| `settlement_records`    | Settlement/payout lines, optionally linked to an order            |
| `freight_rate_cards`    | Configurable courier/zone/service/payment freight weight slabs    |
| `reconciliation_results`| Outcome of comparing an order against a settlement record          |
| `reconciliation_runs`   | One immutable row per reconciliation execution (the run ledger)   |

Design notes:

- All monetary values use `NUMERIC(14, 2)` — never floating point.
- Every table has an integer primary key plus `created_at`/`updated_at`
  timestamps. `raw_imported_records` is append-only, so it only has `created_at`.
- A `MetaData` naming convention gives deterministic constraint names
  (`pk_*`, `fk_*`, `uq_*`, `ix_*`, `ck_*`), which keeps migrations stable.
- Enum-like columns are stored as `VARCHAR` with a `CHECK` constraint
  (`native_enum=False`) so the schema stays portable across databases.
- Reconciliation results are never deleted. A run marks the previous run's rows
  `is_current = false` and tags the new rows with the run that produced them, so
  every past conclusion stays queryable for audit.

### Database migrations (Alembic)

The migration chain in `backend/alembic/versions/` builds the schema up in
five revisions (initial schema → password hash → import mapping support →
reconciliation engine → reconciliation run history). Apply the whole chain once
your hosted database is reachable:

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

## Import pipeline

The import pipeline turns a partner's raw CSV/XLSX into rows stored against
platform-owned **canonical fields**, so downstream logic never has to know that
Flipkart calls a column `Order ID` while a courier calls it `AWB Reference`.

Supported source types (`GET /api/imports/source-types`):

| Source type             | Required canonical fields                          |
| ----------------------- | -------------------------------------------------- |
| Orders                  | `external_order_id`, `order_date`, `order_amount`  |
| Marketplace settlements | `transaction_reference`, `settlement_amount`       |
| COD remittances         | `transaction_reference`, `settlement_amount`       |
| Freight invoices        | `courier_name`, `shipping_charge`                  |
| Returns                 | `external_order_id`, `return_status`               |

The workflow is a four-step lifecycle:

1. **Upload** (`POST /api/imports`) — a CSV/XLSX file plus its source type and
   partner. The uploaded bytes are stored and an `ImportBatch` is created.
2. **Preview** (`GET /api/imports/{id}/preview`) — the parsed headers, sample
   rows and a *suggested* mapping from each header to a canonical field. A
   previously approved mapping for the same source + partner is reused.
3. **Mapping approval** (`PUT /api/imports/{id}/mapping`) — a human confirms or
   edits the mapping. Uncertain suggestions are never auto-approved, and a
   confirmed mapping can be saved for reuse by the same partner.
4. **Process** (`POST /api/imports/{id}/process`) — every row is normalised
   (dates, decimal amounts, currency) and projected onto the canonical fields.
   Processing is blocked until all required fields are mapped.

`GET /api/imports/{id}/records` pages through the stored rows, including the
original raw values alongside the normalised ones and any per-row validation
errors — the raw import is never discarded.

| Endpoint                     | Method | Description                                         |
| ---------------------------- | ------ | --------------------------------------------------- |
| `/api/imports/source-types`  | GET    | Source types + their required fields                 |
| `/api/imports`               | POST   | Upload a file as a new batch (201)                   |
| `/api/imports`               | GET    | List batches (filter by status/source/partner)       |
| `/api/imports/{id}`          | GET    | One batch                                            |
| `/api/imports/{id}/preview`  | GET    | Headers, sample rows and the mapping under review    |
| `/api/imports/{id}/mapping`  | PUT    | Approve/replace the mapping                          |
| `/api/imports/{id}/process`  | POST   | Normalise + project every row                        |
| `/api/imports/{id}/records`  | GET    | Page through stored rows (+ validation errors)       |

## Reconciliation engine

`POST /api/reconciliation/run` recomputes every reconciliation line. It is a
full recompute, but a non-destructive one:

1. **Project** the imported rows onto `orders` and `settlement_records`,
   upserted by natural key so re-runs never duplicate them.
2. **Link** each settlement to the order it settles (by order reference).
3. **Compare** expected against received using exact `Decimal` arithmetic.
4. **Record** one `ReconciliationResult` per order, plus one per settlement that
   could not be tied to any order (categorised `missing_in_orders`) so no
   received money is ever silently discarded.

Statuses: `settled`, `short_paid`, `unpaid_past_due`, `pending`,
`missing_in_orders`. Detected issues: `freight_overcharged`,
`duplicate_settlement`, `missing_reference`, `order_not_found`,
`return_not_received`, `overpaid`.

Key rules:

- `TCS`/`TDS` are **withheld at source** and reported separately; they are
  excluded from revenue leakage and removed from the amount gap before the
  payment state is decided.
- **Revenue leakage** is money due but not received (short-paid or overdue), net
  of withholding; `pending` and unmatched receipts are excluded.
- **Freight overcharge** compares the partner's charged freight against the
  configured rate card (courier + zone + service + payment + weight slab),
  within a configurable tolerance — no courier tariff is hardcoded.
- **Duplicate settlement** lines are flagged and counted once.
- Every run is idempotent: results are derived purely from the projected data,
  so two runs over unchanged data produce the same current results.

Reads default to the latest run; pass `?run_id=` to read a preserved past run.

| Endpoint                        | Method | Description                                    |
| ------------------------------- | ------ | ---------------------------------------------- |
| `/api/reconciliation/run`       | POST   | Recompute all results (finance roles only)      |
| `/api/reconciliation/runs`      | GET    | List runs, newest first (current flagged)       |
| `/api/reconciliation/runs/{id}` | GET    | One run + the results it produced               |
| `/api/reconciliation`           | GET    | List results (filter by status/marketplace/run) |
| `/api/reconciliation/summary`   | GET    | Totals, per-status counts, revenue leakage      |
| `/api/reconciliation/{id}`      | GET    | One result with its supporting evidence         |

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

### Backend

Tests run against in-memory SQLite, so no PostgreSQL instance is needed. The
suite has **259 tests**.

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
cascades), the Alembic migration chain (schema matches the models, roles are
seeded, constraints enforced), CSV/XLSX parsing, mapping suggestion and reuse,
value normalisation, the end-to-end import pipeline, and the reconciliation
engine (partial and multiple settlements, TCS/TDS separation, duplicate
settlements, freight overcharges, run supersession and historical filtering).

### Frontend

The React app is tested with **Vitest** + Testing Library in a jsdom
environment. The suite has **75 tests**.

```bash
# From the frontend/ directory:
npm test                              # run the whole suite (vitest run)
npx vitest run src/api                # run a single folder
```

Coverage includes the import workflow (upload form, mapping editor, history,
records table), the reconciliation screens (summary cards, results table, run
history, detail), the shared formatters, and the typed API clients (endpoint
paths, HTTP methods, query-parameter mapping and error propagation).

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
**Reconciliation**, **Rate Cards**, **Returns** and **Claims**; **Imports** and
**Reconciliation** are fully implemented, the rest are placeholders for
not-yet-built sections.

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
| `pytest`                       | `backend`  | Run the backend test suite       |
| `npm test`                     | `frontend` | Run the frontend test suite      |

## Scope

Implemented:

- The application shell: sidebar navigation, session gating and login screen.
- The PostgreSQL data model (11 tables) and the Alembic migration chain.
- JWT authentication delivered in an HttpOnly cookie, with role-based access
  control (`finance_executive`, `co_founder`).
- The **import pipeline**: CSV/XLSX upload, canonical-field mapping with saved
  per-partner reuse, normalisation and row-level validation, for Orders,
  Marketplace settlements, COD remittances, Freight invoices and Returns.
- The **reconciliation engine**: order↔settlement matching, exact decimal
  comparison, short-paid / unpaid / pending classification, TCS/TDS separation,
  duplicate-settlement detection, freight-overcharge detection against
  configurable rate cards, revenue-leakage reporting and immutable run history.
- The **React UI** for the import workflow and for reconciliation (summary,
  filterable results, order + settlement evidence, run history).

Not yet implemented, by design:

- A CRUD API/UI for freight rate cards (the table and lookup exist; the data is
  populated out of band).
- Returns reconciliation and refund classification beyond storing and
  normalising return rows.
- The `Rate Cards`, `Returns` and `Claims` sidebar sections.
- AI features (e.g. anomaly detection, forecasting).
