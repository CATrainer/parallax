# Parallax

**A UK property opportunity-inference engine.** Parallax issues *briefings* — written, sourced,
confidence-scored findings about specific sites: *"this looks like an inherited home heading for
sale, and it isn't on the market yet."* It is site-first (the unit is a UPRN-anchored
site-opportunity), multi-source (conviction comes from corroboration across independent public
data), and synthesis-led (every headline is a conclusion the engine reasoned to, with its evidence
shown).

Two products on one engine:
- **Product 1 — Parallax** (self-serve): single-site deep-dive, area search, and patch coverage with
  push briefings, validation, watchlist.
- **Product 2 — the broker lens**: the same engine as an owner-situation / transaction-likelihood
  console for mortgage brokers.

---

## What's here

```
parallax/
├── backend/        FastAPI (async) · SQLAlchemy 2 · Celery · the engine (L1–L6)
│   ├── app/
│   │   ├── adapters/   source adapters (CH, Gazette, EPC, HMLR, planning, geocoder)
│   │   ├── engine/     resolution · signals · scoring · synthesis · validation · lenses
│   │   ├── api/        routers + auth + deps
│   │   ├── workers/    Celery app + tasks (ingest → resolve → score → synthesize → validate)
│   │   ├── models/     the spine: Site, Owner, OwnershipLink, Signal, Briefing, Validation, …
│   │   ├── schemas/    typed API contract + standard envelope
│   │   └── seed/        a real Bristol patch (runs the whole app with zero keys)
│   └── Dockerfile, railway.json
├── frontend/       Next.js 14 (App Router, TS strict) · the "briefing, not dashboard" design system
│   └── vercel.json
├── docker-compose.yml
└── .env.example
```

---

## Quickstart — runs locally with **zero API keys**

The app ships with a real, seeded Bristol patch and a deterministic offline synthesizer, so you get
genuine, sourced, confidence-scored briefings immediately — no keys required.

**Prerequisites:** Docker Desktop, Node 18+.

```bash
# 1. Backend stack (Postgres+PostGIS, Redis, API, Celery worker + beat)
cp .env.example .env
docker compose up -d --build

# 2. Seed the Bristol patch (sites, owners, signals → briefings)
docker compose exec api python -m app.seed.run

# 3. Frontend
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Open **http://localhost:3000** and sign in with the prefilled demo account:

> **demo@parallax.dev** / **demo1234** — rung `pro`, 50 validation credits.

- API: http://localhost:8003  (health: `/api/health`, docs: `/docs`)
- Ports are offset (DB 5435, Redis 6380, API 8003, web 3000) to avoid clashes with other local apps.

What to try: **My Patch** (push feed above the conviction floor) → open **14 Mill Lane** (a STRONG
empty/probate briefing) → **Validate this briefing** (spends credits, returns title-confirmed
ownership + occupancy + contact route + provenance) → **Search**, **Watchlist**, and the **Broker**
console (paste addresses → transaction-likelihood briefings).

---

## Setup & API keys (for live data + live AI — add when you're ready)

Everything below is **optional**. The app runs fully on seed data without any of it. Add keys to
`.env`, set `DATA_MODE=LIVE` (and/or per-adapter), and restart (`docker compose up -d`).

| Key in `.env` | Unlocks | Cost | Where to get it |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Live AI synthesis (premium narrative + manufactured conclusions). Without it, the deterministic template synthesizer is used. | Pay-as-you-go | console.anthropic.com → API Keys |
| `COMPANIES_HOUSE_API_KEY` | Live Companies House (distress, PSCs, SPV portfolios). 600 req/5min. | **Free** | developer.company-information.service.gov.uk → register → create an application → REST API key |
| `EPC_AUTH_TOKEN` | Live EPC register (vacancy/refurb signals). | **Free** | get-energy-performance-data.communities.gov.uk → register; the token is your `email:apikey` base64, supplied as the auth token |
| `GEOCODER_PROVIDER` + `IDEAL_POSTCODES_API_KEY` *(or `POSTCODER_API_KEY`)* | Commercial address→UPRN at scale (the §5.2 hard problem). Default is free, keyless `postcodes_io`. | Per-lookup (cached permanently) | ideal-postcodes.co.uk or postcoder.com |
| `HMLR_API_KEY` | Live HMLR title pulls in the **validation tier** (true current owner, ~£3/title). Seeded fixture used otherwise. | Per-title | landregistry → Business Gateway / Data Services |

Notes:
- **AI provider is swappable.** `INFERENCE_PROVIDER=anthropic|openai|template`. Default routes the cheap
  pass to Haiku and the premium pass to Opus; set `template` to force the offline synthesizer.
- **Per-adapter live mode:** flip `DATA_MODE=LIVE` to enable real fetches across adapters; the Celery
  beat schedule then pulls each source on its cadence (CH realtime, Gazette daily, EPC/HMLR monthly,
  planning frequent). In `SEED` the adapters return fixtures and ingestion is a no-op.
- **GDPR:** EPC + probate data are personal data. A documented lawful basis (legitimate-interest
  assessment) is required before going live with real personal data. PII is never logged, never put in
  URLs, never in error messages (enforced in code).

---

## Deploy — Railway (backend) + Vercel (frontend)

> Deploy happens after local sign-off. Steps below are ready to run.

### Railway (API + Postgres + Redis + workers)
1. Create a Railway project. Add plugins: **PostgreSQL** (enable PostGIS — `CREATE EXTENSION postgis;`
   runs automatically on first boot) and **Redis**.
2. Create a service from this repo, root `/backend` (it builds the `Dockerfile`; `railway.json` sets the
   start command to bind `$PORT`). The schema + extensions bootstrap on startup.
3. Add two more services from the same repo/image for the workers, overriding the start command:
   - worker: `celery -A app.workers.celery_app worker --loglevel=info`
   - beat:   `celery -A app.workers.celery_app beat --loglevel=info`
4. Set env vars on all three: `DATABASE_URL` (Railway Postgres, as `postgresql+asyncpg://…`),
   `REDIS_URL`, `ENVIRONMENT=production`, `JWT_SECRET` (strong), `DATA_MODE`, and any API keys.
5. One-off seed (optional, for a demo): `railway run python -m app.seed.run`.

### Vercel (frontend)
1. Import the repo, root `/frontend` (Vercel auto-detects Next.js; `vercel.json` is present).
2. Set env var `NEXT_PUBLIC_API_BASE` = your Railway API URL (e.g. `https://parallax-api.up.railway.app`).
3. Deploy. Then set `FRONTEND_ORIGIN` = your Vercel URL on the Railway API service so CORS allows it.

---

## Engine, briefly (the moat is L2–L5)

| Layer | Does | Moat |
|---|---|---|
| L1 Ingestion | Pull each source on its cadence into the raw store (dumb adapters). | — |
| L2 Resolution | Resolve everything to a canonical `Site` (UPRN) + `Owner`; probabilistic, scored links. | ★ spine |
| L3 Signals | Raw records → typed, time-stamped, sourced weak signals with decay. | ★ |
| L4 Synthesis | AI fuses signals into a sourced narrative + manufactured conclusions. | ★ hero |
| L5 Scoring/Validation | Conviction per opportunity (noisy-OR corroboration); gated paid validation. | ★ |
| L6 Lenses | Saved filters/views per client type. | — |

Conviction bands: **LOW** 0–30 · **MONITOR** 31–55 · **LIKELY** 56–80 · **STRONG** 81–100.
Push floor defaults to MONITOR (31), adjustable per patch.
