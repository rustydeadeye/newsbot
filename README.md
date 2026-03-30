# Newsbot

India-focused finance news automation service built with FastAPI and Postgres/Supabase.

## Components

- `app/api`: HTTP endpoints for health, sources, events, and review queue
- `app/workers`: ingestion, normalization, drafting, and publishing workers
- `frontend`: Next.js dashboard for review, drafts, events, and settings
- `supabase/schema.sql`: database schema for Supabase/Postgres
- `tests`: baseline unit tests for core pipeline behavior

## Run

```bash
uvicorn app.main:app --reload
```

Dashboard:

```bash
cd frontend
npm install
npm run dev
```

## Environment

Create a `.env` with:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/newsbot
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
X_API_BASE_URL=https://api.x.com/2
X_BEARER_TOKEN=...
AUTO_POST_THRESHOLD=80
```

Create `frontend/.env.local` with:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Deployment

The app is designed for Fly.io with one web process and one or more worker processes. Redis is not required; job claiming uses Postgres row locking.
