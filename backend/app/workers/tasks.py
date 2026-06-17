"""Celery tasks (BUILD_SPEC §Celery contract).

The ingestion → resolution → scoring → synthesis pipeline plus the validation worker. Each
task opens its OWN async session and drives the coroutine via ``_run`` (``asyncio.run``) — it
never reuses a request session (§3.3). Every task is defensive: a single bad record/site is
logged and skipped, never crashing the worker.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import get_logger
from app.workers.celery_app import celery_app

log = get_logger("parallax.tasks")

# A long-lived Celery worker invokes ``asyncio.run`` once per task, creating a fresh event
# loop each time. The app's global async engine binds its asyncpg pool to the FIRST loop it
# touches, so reusing it on a later task fails with "attached to a different loop". We give
# every task its OWN engine + sessionmaker, bound to that task's loop and disposed after.
_session_factory: ContextVar[async_sessionmaker] = ContextVar("_task_session_factory")


def _session():
    """Open a session from the current task's per-loop factory."""
    return _session_factory.get()()


def _run(coro) -> Any:
    """Drive a coroutine in a fresh loop with a fresh engine bound to that loop."""

    async def _wrap():
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        token = _session_factory.set(factory)
        try:
            return await coro
        finally:
            _session_factory.reset(token)
            await engine.dispose()

    return asyncio.run(_wrap())


# ─────────────────────────────────────── ingest_source ───────────────────────────────────────────
@celery_app.task(name="app.workers.tasks.ingest_source")
def ingest_source(name: str) -> dict:
    """Pull a source via its adapter, store RawRecords, enqueue extraction per raw."""
    return _run(_ingest_source(name))


async def _ingest_source(name: str) -> dict:
    from app.adapters.registry import get_adapter
    from app.models.entities import RawRecord

    adapter = get_adapter(name)
    stored = 0
    async with _session() as db:
        try:
            raws = await adapter.fetch()
        except Exception:  # noqa: BLE001 — adapter failure is logged, never crashes the beat
            log.warning("ingest_fetch_failed", source=name)
            raws = []

        raw_ids: list[str] = []
        for raw in raws or []:
            try:
                item = adapter.normalise(raw)
            except Exception:  # noqa: BLE001 — skip a malformed record
                log.warning("ingest_normalise_failed", source=name)
                continue
            record = RawRecord(
                source=item.source,
                source_ref=item.source_ref,
                source_version=item.source_version,
                payload=item.payload or {},
                fetched_at=item.fetched_at,
            )
            db.add(record)
            await db.flush()
            raw_ids.append(record.id)
            stored += 1
        await db.commit()

    for rid in raw_ids:
        try:
            resolve_and_extract.delay(rid)
        except Exception:  # noqa: BLE001 — queue hiccup; the record is persisted for retry
            log.warning("ingest_enqueue_failed", source=name)

    log.info("ingest_complete", source=name, stored=stored)
    return {"source": name, "stored": stored}


# ──────────────────────────────────── resolve_and_extract ────────────────────────────────────────
@celery_app.task(name="app.workers.tasks.resolve_and_extract")
def resolve_and_extract(raw_id: str) -> dict:
    """Load a raw record, extract signals (resolution happens inside), enqueue synthesis."""
    return _run(_resolve_and_extract(raw_id))


async def _resolve_and_extract(raw_id: str) -> dict:
    from app.engine.signals import extract_signals
    from app.models.entities import RawRecord

    uprns: set[str] = set()
    async with _session() as db:
        raw = await db.get(RawRecord, raw_id)
        if raw is None:
            log.warning("extract_raw_missing", raw_id=raw_id)
            return {"raw_id": raw_id, "signals": 0}
        try:
            signals = await extract_signals(db, raw)
        except Exception:  # noqa: BLE001
            log.warning("extract_failed", raw_id=raw_id)
            signals = []
        uprns = {s.site_uprn for s in signals if getattr(s, "site_uprn", None)}
        await db.commit()

    for uprn in uprns:
        try:
            score_and_synthesize.delay(uprn)
        except Exception:  # noqa: BLE001
            log.warning("synth_enqueue_failed", uprn=uprn)

    log.info("extract_complete", raw_id=raw_id, signals=len(uprns))
    return {"raw_id": raw_id, "sites": list(uprns)}


# ──────────────────────────────────── score_and_synthesize ───────────────────────────────────────
@celery_app.task(name="app.workers.tasks.score_and_synthesize")
def score_and_synthesize(uprn: str) -> dict:
    """(Re)score a site and synthesise/persist its briefing."""
    return _run(_score_and_synthesize(uprn))


async def _score_and_synthesize(uprn: str) -> dict:
    from app.engine.synthesis import synthesize_briefing

    async with _session() as db:
        try:
            briefing = await synthesize_briefing(db, uprn, premium=True)
            await db.commit()
            log.info("synth_complete", uprn=uprn, conviction=briefing.conviction, band=briefing.band)
            return {"uprn": uprn, "conviction": briefing.conviction, "band": briefing.band}
        except Exception:  # noqa: BLE001
            await db.rollback()
            log.warning("synth_failed", uprn=uprn)
            return {"uprn": uprn, "error": "synthesis_failed"}


# ───────────────────────────────────── run_validation_task ───────────────────────────────────────
@celery_app.task(name="app.workers.tasks.run_validation_task")
def run_validation_task(validation_id: str) -> dict:
    """Run the validation tier and reconcile the user's credit balance to the actual cost."""
    return _run(_run_validation(validation_id))


# The estimate the API debited optimistically at /validate — reconciled here.
_OPTIMISTIC_DEBIT = 3


async def _run_validation(validation_id: str) -> dict:
    from app.engine.validation import run_validation
    from app.models.entities import User, Validation

    async with _session() as db:
        validation = await db.get(Validation, validation_id)
        if validation is None:
            log.warning("validation_missing", validation_id=validation_id)
            return {"validation_id": validation_id, "error": "not_found"}

        try:
            validation = await run_validation(db, validation_id)  # flushes, does not commit
        except Exception:  # noqa: BLE001 — never crash the worker
            await db.rollback()
            log.warning("validation_run_failed", validation_id=validation_id)
            return {"validation_id": validation_id, "error": "failed"}

        # Reconcile credits: the API already debited the estimate; adjust to actual spend.
        actual = int(validation.credits_spent or 0)
        if validation.user_id:
            user = (
                await db.execute(select(User).where(User.id == validation.user_id))
            ).scalar_one_or_none()
            if user is not None:
                delta = actual - _OPTIMISTIC_DEBIT  # >0 = debit more; <0 = refund
                user.credits_remaining = max(0, (user.credits_remaining or 0) - delta)

        await db.commit()
        log.info(
            "validation_task_complete",
            validation_id=validation_id,
            status=validation.status,
            credits_spent=actual,
        )
        return {
            "validation_id": validation_id,
            "status": validation.status,
            "credits_spent": actual,
        }
