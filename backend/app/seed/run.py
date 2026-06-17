"""Reseed entrypoint: `python -m app.seed.run`.

Seeds entities + signals (idempotent), commits, then synthesises a briefing for every
seeded site so the UI shows value with no keys. Synthesis is wrapped defensively so this
file is robust to build order — if the engine module isn't present yet, it just logs.
"""
from __future__ import annotations

import asyncio

from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.seed.seed_data import SITES, seed

log = get_logger("seed.run")


async def _synthesize_all(db) -> int:
    """Best-effort briefing synthesis for each seeded site. Returns count synthesised."""
    try:
        from app.engine.synthesis import synthesize_briefing  # noqa: PLC0415
    except Exception as exc:  # engine not built yet, or import error
        log.warning("synthesis_unavailable", error=str(exc))
        return 0

    count = 0
    for row in SITES:
        uprn = row[0]
        try:
            await synthesize_briefing(db, uprn)
            await db.commit()
            count += 1
        except Exception as exc:
            await db.rollback()
            log.warning("synthesis_failed", uprn=uprn, error=str(exc))
    return count


async def main() -> None:
    configure_logging()
    async with SessionLocal() as db:
        summary = await seed(db)
        await db.commit()
        synthesised = await _synthesize_all(db)

    print("Parallax seed complete:")
    for k, v in summary.items():
        print(f"  {k:>10}: {v}")
    print(f"  {'briefings':>10}: {synthesised}")
    print("Demo login: demo@parallax.dev / demo1234 (rung=pro, 50 credits)")


if __name__ == "__main__":
    asyncio.run(main())
