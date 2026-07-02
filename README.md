# Customer Re-Engagement AI Copilot

A single-tenant campaign workbench for re-engaging customers with ranked recommendations, consent-aware channel selection, editable email/SMS drafts, and mock sending.

The local demo defaults to `AI_PROVIDER=mock`, so it runs end-to-end without paid OpenAI API calls. Set `AI_PROVIDER=openai` and provide `OPENAI_API_KEY` when you want real model calls.

## Features

- CSV customer upload with purchase history
- Idempotent demo seed data
- Postgres + pgvector schema with `vector(1536)` embeddings
- LangGraph 8-node campaign workflow
- Deterministic customer scoring with visible score breakdowns
- Consent-aware email/SMS channel decisions
- Draft review, edit, approve, reject, regenerate, and mock-send
- Campaign CSV export
- No authentication, no JWT/session logic

## Architecture

```text
Browser
  |
  v
Next.js frontend :3000
  |
  v
FastAPI backend :8000
  |
  +--> LangGraph workflow
  |      analyze product -> retrieve customers -> RAG context -> score
  |      -> channel decision -> generate drafts -> compliance loop -> save
  |
  v
Postgres + pgvector :5432
```

## Local Setup

Prerequisites:

- Docker Desktop
- Node.js 24+ only if you want to run the frontend outside Docker

Run the full stack:

```bash
docker compose up --build
```

Seed demo data:

```bash
curl -X POST http://localhost:8000/demo/seed
```

Open:

```text
http://localhost:3000
```

Expected checkpoint:

1. Click `Seed Demo Data`.
2. Go to `Customers`; 5 customers appear and Emily Johnson is `Unsubscribed`.
3. Go to `Campaign`; run the default headphones campaign.
4. Results show 4 ranked customers; Emily is excluded.
5. Expand a row, edit a draft, approve it, mock send it, regenerate another draft, and export CSV.

Backend only:

```bash
docker compose up --build postgres backend
curl -X POST http://localhost:8000/demo/seed
curl http://localhost:8000/customers
```

Standalone workflow:

```bash
docker compose exec backend python run_workflow.py
```

Frontend outside Docker:

```bash
cd frontend
npm install
npm run dev
```

## Environment Variables

Backend:

```text
DATABASE_URL=postgresql+psycopg2://copilot:copilot@postgres:5432/copilot
AI_PROVIDER=mock
OPENAI_API_KEY=dummy-key-for-local-mock-mode
OPENAI_MODEL=gpt-4.1-mini
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
CORS_ORIGIN_REGEX=https://.*\.vercel\.app
```

Frontend:

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## LangGraph Workflow

1. `analyze_product_node`: analyzes product name, description, category, and offer into `ProductAnalysis`.
2. `retrieve_customers_node`: retrieves customers where `unsubscribed=false`, email or SMS consent is true, and purchase history exists.
3. `rag_context_node`: computes product-to-purchase similarity and returns top 2 purchase matches per customer.
4. `score_customers_node`: deterministic 0-100 buyer score:
   - product similarity: 35%
   - purchase recency: 25%
   - purchase frequency: 20%
   - lifetime value: 10%
   - engagement score: 10%
5. `filter_and_channel_decision_node`: skips unsubscribed/score `<50`; chooses email, SMS, or both by consent and `score>=75`.
6. `generate_drafts_node`: generates drafts for top 20 eligible customers.
7. `compliance_check_node`: verifies consent, unsubscribe/STOP text, and unsupported claims; retries twice before manual review.
8. `save_results_node`: writes `campaign_results` and `drafts`.

## API Reference

- `GET /health`
- `POST /demo/seed`
- `GET /customers`
- `POST /customers/upload`
- `POST /campaigns`
- `GET /campaigns/{id}`
- `GET /campaigns/{id}/results`
- `GET /campaigns/{id}/export`
- `POST /drafts/{id}/regenerate`
- `PATCH /drafts/{id}`
- `POST /drafts/{id}/approve`
- `POST /drafts/{id}/reject`
- `POST /drafts/{id}/send-mock`

`POST /campaigns` runs the workflow synchronously and persists `running`, `completed`, or `failed` status on the campaign.

`PATCH /drafts/{id}` always resets the draft to `pending_review`.

## DB Schema

- `customers`: customer identity, consent flags, unsubscribe flag, lifetime value, engagement score
- `products`: product catalog with `embedding vector(1536)`
- `purchases`: historical purchases with `embedding vector(1536)`
- `campaigns`: product launch campaign and workflow status
- `campaign_results`: ranked result per campaign/customer, unique on `(campaign_id, customer_id)`
- `drafts`: generated/editable email and SMS copy, one draft per campaign result

Important constraints:

- `customers.email` unique
- `campaign_results(campaign_id, customer_id)` unique
- campaign status: `draft`, `running`, `completed`, `failed`
- draft status: `pending_review`, `approved`, `rejected`, `regenerated`, `sent_mock`

## Deployment: Neon + Render + Vercel

Deploy in this order.

### 1. Neon Database

1. Create a Neon Postgres project.
2. Enable pgvector in the database:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

3. Copy the pooled or direct connection string.
4. Use SQLAlchemy format for the backend:

```text
postgresql+psycopg2://USER:PASSWORD@HOST/DB?sslmode=require
```

### 2. Render Backend

Create a Render Web Service from this repo.

Settings:

```text
Root Directory: backend
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Environment:

```text
DATABASE_URL=<Neon SQLAlchemy connection string>
AI_PROVIDER=mock
OPENAI_API_KEY=dummy-key-for-local-mock-mode
OPENAI_MODEL=gpt-4.1-mini
CORS_ORIGINS=https://<your-vercel-app>.vercel.app
CORS_ORIGIN_REGEX=https://.*\.vercel\.app
```

For real OpenAI calls later:

```text
AI_PROVIDER=openai
OPENAI_API_KEY=<real key>
```

After deploy:

```bash
curl https://<your-render-service>.onrender.com/health
curl -X POST https://<your-render-service>.onrender.com/demo/seed
```

### 3. Vercel Frontend

Create a Vercel project from this repo.

Settings:

```text
Root Directory: frontend
Framework Preset: Next.js
Build Command: npm run build
Output: .next
```

Environment:

```text
NEXT_PUBLIC_API_URL=https://<your-render-service>.onrender.com
```

The backend allows exact `CORS_ORIGINS` plus Vercel-generated domains matched by:

```text
CORS_ORIGIN_REGEX=https://.*\.vercel\.app
```

That keeps Vercel preview and generated production aliases working without another backend edit.

## Future Improvements

- Real SendGrid and Twilio sends
- A/B testing
- Campaign performance tracking
- CRM sync
- Celery/Redis background jobs
- Auth and multi-tenant workspaces
