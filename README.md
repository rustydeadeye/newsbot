# Newsbot

India-focused finance news automation service built with FastAPI and Supabase Postgres.

## Components

- `app/api`: HTTP endpoints for health, sources, events, and review queue
- `app/workers`: ingestion, normalization, drafting, and publishing workers
- `frontend`: Next.js dashboard for review, drafts, events, and settings
- `supabase/schema.sql`: database schema for Supabase/Postgres
- `tests`: baseline unit tests for core pipeline behavior

## Environment

Create a `.env` with:

```env
DATABASE_URL=postgresql+psycopg://postgres.vvndcdlvurordmdqozql:[YOUR-SUPABASE-DB-PASSWORD]@db.vvndcdlvurordmdqozql.supabase.co:5432/postgres
SUPABASE_URL=https://vvndcdlvurordmdqozql.supabase.co
SUPABASE_PUBLISHABLE_KEY=...
SUPABASE_JWT_SECRET=... # optional if your project still uses symmetric JWT signing
AUTH_ADMIN_EMAILS=admin@example.com
AUTH_AUTO_PROVISION_USERS=true
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
X_API_BASE_URL=https://api.x.com/2
X_CLIENT_ID=...
X_CLIENT_SECRET=... # optional for public PKCE clients
X_ACCESS_TOKEN=...
X_REFRESH_TOKEN=...
X_TOKEN_URL=https://api.x.com/2/oauth2/token
AUTO_POST_THRESHOLD=80
```

Create `frontend/.env.local` with:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_SUPABASE_URL=https://vvndcdlvurordmdqozql.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=...
```

The default database target for this project is the Supabase project `vvndcdlvurordmdqozql`. The checked-in schema lives in `supabase/schema.sql` and should be treated as the current source of truth for initialization.

## Auth And Roles

- The frontend now uses Supabase Auth sessions with SSR-safe cookies.
- The FastAPI backend verifies Supabase bearer tokens and maps authenticated users into `workspace_users`.
- The first user whose email is listed in `AUTH_ADMIN_EMAILS` is provisioned as `admin`; other new users default to `customer`.
- `customer` users can review drafts, edit customer-safe settings, and view simplified lifecycle state.
- `admin` users can also access publishing, source coverage, and operational controls.
- If you want to disable automatic provisioning, set `AUTH_AUTO_PROVISION_USERS=false` and seed `workspace_users` yourself.

## Run

Install dependencies:

```bash
.venv/bin/python -m pip install -e '.[dev]'
cd frontend
npm install
```

Start the API:

```bash
uvicorn app.main:app --reload
```

Dashboard:

```bash
cd frontend
npm run dev
```

## Supabase MCP

This workspace includes a project-level MCP config at `.vscode/mcp.json` for the hosted Supabase MCP server.

- The server URL is already scoped to this workspace's Supabase project.
- The MCP config uses a secure password-style input for the Supabase personal access token instead of storing the token in git.
- On first start, VS Code prompts for the token and stores it securely for later runs.
- Use this MCP connection for schema inspection and follow-up database operations against the default project.

If your client supports Supabase OAuth directly, you can remove the `Authorization` header from `.vscode/mcp.json` and use the hosted login flow instead.

## Deployment

The app is designed for Fly.io with one web process and one or more worker processes. Redis is not required; job claiming uses Postgres row locking.

For posting to X, the app now expects OAuth 2.0 user-context tokens for the authenticated account. `X_ACCESS_TOKEN` is used for posting, and `X_REFRESH_TOKEN` is used to refresh it when X returns `401`. Keep both tokens out of git.
