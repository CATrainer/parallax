# Parallax — internal build contract (read before writing code)

Monorepo: `backend/` (FastAPI async) + `frontend/` (Next.js 14 App Router). Full product
brief lives in the conversation; this file is the **integration contract** so independently-built
modules fit together. Obey it exactly — signatures here are load-bearing.

## Golden rules (§3.3)
- Python 3.12, async everywhere. `httpx` async only, never `requests`. Wrap external calls in
  try/except + structlog. No blocking the request thread — heavy work runs in Celery tasks.
- All endpoints return the envelope in `app/schemas/common.py` (`ok()` / `err()`), never raw dicts.
- Secrets via `app.core.config.settings` only. Never hardcode, never log. **No PII in logs/URLs/errors.**
- UPRN is the canonical site key. Scores/briefings are computed in workers and **persisted**, not per-request.
- Every source behind an adapter (`app/adapters/base.py`). Adapters normalise; they never infer.
- **SEED vs LIVE:** `settings.data_mode`. In SEED (default, zero keys) adapters return fixture data and
  the app must run fully. In LIVE they hit real APIs. Synthesis falls back to a deterministic template
  when `settings.has_anthropic` is False — the app NEVER hard-depends on a key to run locally.

## Foundation already written (DO NOT recreate; import from these)
- `app/core/config.py` → `settings`
- `app/core/db.py` → `Base`, `engine`, `SessionLocal`, `get_db`
- `app/core/logging.py` → `get_logger`, `configure_logging`
- `app/models/` → SQLAlchemy: `Site, Owner, OwnershipLink, Signal, Briefing, Validation, User, Patch,
  WatchlistItem, RawRecord, GeocodeCache`; enums incl. `Band, SignalType, OpportunityType, band_for(score)`.
- `app/schemas/common.py` → envelope; `app/schemas/domain.py` → all API I/O models.
- `app/adapters/base.py` → `SourceAdapter`, `Geocoder`, `RawItem`, `GeocodeMatch`.

## Public engine contract (these signatures are fixed — implement/consume exactly)

`app/engine/resolution.py`
- `async def resolve_site(db, address: str, postcode: str | None = None, *, paon=None, saon=None,
   property_type=None, local_authority=None) -> Site`  — normalise addr, geocode (cached), upsert Site.
- `async def resolve_owner(db, *, owner_type: str, display_name: str, company_number: str | None = None,
   dob_month=None, dob_year=None, last_known_address=None) -> Owner` — fuzzy upsert.
- `async def link_ownership(db, site, owner, role, source, link_confidence, is_current=True) -> OwnershipLink`

`app/engine/signals.py`
- `async def extract_signals(db, raw: RawRecord) -> list[Signal]` — raw record → typed Signals (persisted).
- `SIGNAL_CATALOGUE: dict[str, dict]` with strength/decay per `signal_type` from the brief §6.2.

`app/engine/scoring.py`
- `@dataclass ScoreResult: conviction:int; band:str; headline_opportunity:str|None;
   opportunity_scores:dict[str,int]; matched_opportunity_types:list[str]; signal_ids:list[str]`
- `def score_signals(signals: list[Signal]) -> ScoreResult` — pure; graceful degradation; multi-signal rule
  (≥3 independent corroborating sources ⇒ lead-grade; 1 ⇒ flagged candidate).
- `async def rescore_site(db, uprn: str) -> ScoreResult` — load signals, score, used by synthesis.

`app/engine/synthesis.py`
- `async def synthesize_briefing(db, uprn: str, *, premium: bool = True) -> Briefing` — score, build prose
  with cited_signal_ids, manufactured conclusions, persist Briefing, return it. Uses InferenceProvider;
  template fallback when no key. Guardrails: assert only what signals support; phrase inference as inference.

`app/engine/inference.py`
- `class InferenceProvider(Protocol): async def complete(self, task: str, payload: dict) -> dict`
- `def get_provider(tier: Literal["cheap","premium"]) -> InferenceProvider` — routes via settings;
  providers: `AnthropicProvider`, `TemplateProvider` (deterministic, no network).

`app/engine/validation.py`
- `async def run_validation(db, validation_id: str) -> Validation` — escalating cost order
  (cheap CH/web → title pull → human). Writes provenance_log + ValidationResult fields. Debits credits.

`app/engine/lenses.py`
- `OPPORTUNITY_TAXONOMY: dict[str, dict]` (signal bundles per §7.1).
- `def opportunities_for(signals) -> list[tuple[str, float]]` — (opportunity_type, score 0-1).

## Celery contract
`app/workers/celery_app.py` exposes `celery_app`. Tasks in `app/workers/tasks.py`:
`ingest_source.delay(name)`, `resolve_and_extract.delay(raw_id)`, `score_and_synthesize.delay(uprn)`,
`run_validation_task.delay(validation_id)`. Beat schedule wires source cadences. Tasks open their own
async session (use `asyncio.run` wrapper) — do not reuse request sessions.

## API contract (routers in `app/api/routers/`, mounted under `/api` in `app/main.py`)
Endpoints exactly per brief §8.2/§8.3. Auth via bearer JWT (`app/api/auth.py`). `get_current_user`
dependency in `app/api/deps.py`. Dev convenience: a seeded demo user `demo@parallax.dev` / `demo1234`,
rung `pro`, 50 credits. Endpoints: search, sites/{uprn}, sites/{uprn}/briefing, sites/{uprn}/validate(POST),
validations/{id}, patch (GET/POST), patch/briefings, watchlist (GET/POST), sites/{uprn}/status(POST),
usage, broker/enrich, broker/site/{uprn}/intelligence, plus auth/register, auth/login, auth/me.

## Frontend contract (`frontend/`)
Next.js 14 App Router, TS strict, Tailwind, design tokens §9 exactly (paper/ink/seal, Newsreader serif +
Inter + IBM Plex Mono). "Briefing, not dashboard." API base from `NEXT_PUBLIC_API_BASE`. Surfaces:
Briefing page (hero, §9.3), My Patch (push feed), Search (pull), Watchlist, Broker console, Login.
Action bar must never overlap mid-scroll content. Responsive, visible focus, reduced-motion, real empty states.

## Seed data (`app/seed/seed_data.py`)
A real Bristol (BS) patch: ~25 sites with realistic addresses/UPRNs, owners (companies + individuals),
ownership links, and a spread of signals across the catalogue so scoring yields a believable mix of bands
and at least several LIKELY/STRONG probate-vacant + empty-property briefings. `async def seed(db)` is
idempotent (upsert). After seeding entities+signals, it calls scoring+synthesis to persist briefings so the
UI shows value immediately with no keys. Expose `python -m app.seed.run` to (re)seed.
