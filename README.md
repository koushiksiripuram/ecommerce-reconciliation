# E-commerce Financial Reconciliation Platform

Foundation for a financial reconciliation platform built for a D2C home textiles
business. This repository currently contains **project scaffolding only** — no
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
│   ├── requirements.txt        # Python dependencies
│   ├── alembic.ini             # Alembic configuration (DB URL supplied at runtime)
│   ├── alembic/
│   │   ├── env.py              # Migration environment; reads settings + Base.metadata
│   │   ├── script.py.mako      # Template for generated migration files
│   │   └── versions/           # Generated migration scripts live here
│   └── app/
│       ├── main.py             # FastAPI application entry point (app + CORS + router)
│       ├── api/
│       │   ├── router.py       # Aggregates all route modules under the API prefix
│       │   └── routes/
│       │       └── health.py   # GET /api/health
│       ├── core/
│       │   └── config.py       # Environment-driven settings + database URL
│       └── db/
│           ├── base.py         # SQLAlchemy DeclarativeBase for models
│           └── session.py      # Engine, sessionmaker, get_db dependency
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
- PostgreSQL 14+ (required only for migrations/runtime database access, not for
  starting the API or the health check)

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

| Variable            | Description                                        | Default            |
| ------------------- | -------------------------------------------------- | ------------------ |
| `APP_NAME`          | Application title shown in the OpenAPI docs         | — |
| `ENVIRONMENT`       | Deployment environment label                        | `development`      |
| `DEBUG`             | Enables FastAPI debug mode                          | `true`             |
| `API_PREFIX`        | Prefix applied to all API routes                    | `/api`             |
| `CORS_ORIGINS`      | JSON array of allowed frontend origins              | `["http://localhost:5173"]` |
| `POSTGRES_HOST`     | PostgreSQL host                                     | `localhost`        |
| `POSTGRES_PORT`     | PostgreSQL port                                     | `5432`             |
| `POSTGRES_USER`     | PostgreSQL user                                     | `postgres`         |
| `POSTGRES_PASSWORD` | PostgreSQL password                                 | `postgres`         |
| `POSTGRES_DB`       | PostgreSQL database name                            | `reconciliation`   |

> `CORS_ORIGINS` must be valid JSON, e.g. `["http://localhost:5173","https://app.example.com"]`.

### Database migrations (Alembic)

The database URL is derived from the `POSTGRES_*` variables in `backend/.env`,
so it never needs to be repeated in `alembic.ini`.

```bash
# From the backend/ directory, with the virtualenv active:
alembic revision --autogenerate -m "create initial tables"
alembic upgrade head
```

Alembic discovers models via `app/db/base.py::Base`. Import new models in
`alembic/env.py` so they are registered before autogenerate runs.

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

## Scope

Not yet implemented, by design: authentication, AI features, file uploads, and
reconciliation logic.
