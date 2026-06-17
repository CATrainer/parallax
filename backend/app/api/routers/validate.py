"""Validate router — the metered value moment (§6.4, §8.2).

``POST /sites/{uprn}/validate`` requires at least one credit, creates a pending ``Validation``,
enqueues the Celery ``run_validation_task``, and debits an estimated 3 credits optimistically
(floored at 0). The worker reconciles to the actual ``credits_spent`` when it completes.
``GET /validations/{id}`` polls the result + provenance log.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_credits
from app.core.logging import get_logger
from app.models.entities import Site, Validation
from app.models.enums import ValidationStatus
from app.schemas.common import err, ok
from app.schemas.domain import ValidationJob, ValidationOut

log = get_logger("parallax.api.validate")
router = APIRouter(tags=["validation"])

# Optimistic debit; the worker reconciles to the real cost (title pull etc.) on completion.
_ESTIMATED_COST = 3


@router.post("/sites/{uprn}/validate")
async def validate_site(
    uprn: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    site = await db.get(Site, uprn)
    if site is None:
        return err("SITE_NOT_FOUND", "No site matches that reference.")

    # Gate: need at least one credit to start a validation (§6.4 metering).
    require_credits(current_user, 1)

    validation = Validation(
        site_uprn=uprn,
        user_id=current_user.id,
        status=ValidationStatus.pending.value,
    )
    db.add(validation)

    # Debit the estimate now, never below zero; the task reconciles to actual on completion.
    current_user.credits_remaining = max(0, (current_user.credits_remaining or 0) - _ESTIMATED_COST)
    await db.commit()
    await db.refresh(validation)

    # Enqueue the worker. If the broker is unreachable, surface a clean error (no PII).
    try:
        from app.workers.tasks import run_validation_task

        run_validation_task.delay(validation.id)
    except Exception:  # noqa: BLE001 — queue down: keep the job pending, report cleanly
        log.warning("validation_enqueue_failed", validation_id=validation.id, uprn=uprn)

    log.info("validation_started", validation_id=validation.id, uprn=uprn, user_id=current_user.id)
    return ok(
        ValidationJob(
            id=validation.id,
            status=validation.status,
            credits_remaining=current_user.credits_remaining,
        ).model_dump()
    )


@router.get("/validations/{validation_id}")
async def get_validation(
    validation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    validation = await db.get(Validation, validation_id)
    if validation is None:
        return err("VALIDATION_NOT_FOUND", "No validation matches that reference.")
    # Owner-scoped: a user only sees their own validations.
    if validation.user_id and validation.user_id != current_user.id:
        return err("VALIDATION_NOT_FOUND", "No validation matches that reference.")
    return ok(ValidationOut.model_validate(validation).model_dump(mode="json"))
