"""L5 — Scoring (§6.4).

Conviction (0–100) per opportunity type = a weighted blend over present signals, with
**graceful degradation** (a missing signal only lowers the score and widens uncertainty —
it never errors) and the **multi-signal rule** (≥3 independent corroborating sources →
lead-grade; 1 source → a flagged, capped "needs validation" candidate). The distinction
*is* the product.

``score_signals`` is pure. ``rescore_site`` loads a site's signals and scores them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.logging import get_logger
from app.engine import lenses
from app.engine.signals import decay_factor
from app.models.entities import Signal
from app.models.enums import band_for

log = get_logger("engine.scoring")

# A single-source candidate is capped here — surfaced, but flagged "needs validation" (§6.4).
_SINGLE_SOURCE_CAP = 55
# ≥ this many independent sources ⇒ "lead-grade".
_LEAD_GRADE_SOURCES = 3


@dataclass
class ScoreResult:
    conviction: int
    band: str
    headline_opportunity: str | None
    opportunity_scores: dict[str, int]
    matched_opportunity_types: list[str]
    signal_ids: list[str] = field(default_factory=list)


def _independent_sources(signals: list[Signal], sig_types: set[str]) -> set[str]:
    """Distinct sources among fired signals whose type is in the bundle — the corroboration count."""
    sources: set[str] = set()
    for s in signals:
        if not getattr(s, "fired", True):
            continue
        if s.signal_type in sig_types:
            sources.add(s.source or s.signal_type)
    return sources


def score_signals(signals: list[Signal]) -> ScoreResult:
    """Pure scoring over a site's signals. Never raises on sparse/empty input.

    For each opportunity type in the taxonomy we compute a decayed, strength-weighted blend,
    normalise to 0–100, then apply the multi-signal rule. Headline = highest-scoring type.
    """
    now = datetime.now(timezone.utc)
    fired = [s for s in signals if getattr(s, "fired", True)]

    opportunity_scores: dict[str, int] = {}
    # per-opportunity contributing signal ids, for headline attribution
    contributing: dict[str, list[str]] = {}

    for opp_type, spec in lenses.OPPORTUNITY_TAXONOMY.items():
        weights: dict[str, float] = spec["weights"]
        sig_types = set(weights)
        total_weight = sum(weights.values()) or 1.0

        # Gate: required_any / required_all must be satisfied by *fired* signals.
        present_types = {s.signal_type for s in fired if s.signal_type in sig_types}
        required_any = spec.get("required_any") or []
        if required_any and not (present_types & set(required_any)):
            continue
        required_all = spec.get("required_all") or []
        if required_all and not set(required_all).issubset(present_types):
            continue

        # Noisy-OR accumulation: conviction compounds from corroboration rather than being
        # diluted by an average (§0, §6.4 — "conviction comes from corroboration across
        # independent sources"). Each firing signal contributes evidence; independent
        # corroborators push the probability toward 1, so a genuinely strong, multi-source
        # case can reach STRONG while a lone weak signal stays low.
        prob_not = 1.0
        ids: list[str] = []
        for sig_type, weight in weights.items():
            best = 0.0
            best_id = None
            for s in fired:
                if s.signal_type != sig_type:
                    continue
                strength = float(getattr(s, "strength", 0.0) or 0.0)
                d = decay_factor(getattr(s, "decays", "slow") or "slow", getattr(s, "observed_at", None), now)
                val = strength * d
                if val > best:
                    best = val
                    best_id = getattr(s, "id", None)
            if best > 0:
                # ``weight`` is the signal's importance in this bundle; relative to the
                # bundle's heaviest weight so the defining signal carries full force.
                importance = weight / max(weights.values())
                contribution = min(0.95, importance * best)
                prob_not *= 1.0 - contribution
                if best_id is not None:
                    ids.append(best_id)

        raw_score = 1.0 - prob_not

        # Multi-signal rule (§6.4). Independent sources = corroboration count.
        sources = _independent_sources(fired, sig_types)
        if len(sources) >= _LEAD_GRADE_SOURCES:
            # Lead-grade: independent corroboration lifts conviction into decision range.
            raw_score = min(1.0, raw_score * 1.25 + 0.05)
        raw_score = max(0.0, min(1.0, raw_score))
        score = int(round(raw_score * 100))
        if len(sources) <= 1:
            # Single-source candidate: surfaced, but capped + flagged "needs validation".
            score = min(score, _SINGLE_SOURCE_CAP)

        if score > 0:
            opportunity_scores[opp_type] = score
            contributing[opp_type] = ids

    if not opportunity_scores:
        return ScoreResult(
            conviction=0,
            band=band_for(0).value,
            headline_opportunity=None,
            opportunity_scores={},
            matched_opportunity_types=[],
            signal_ids=[],
        )

    headline = max(opportunity_scores, key=lambda k: opportunity_scores[k])
    conviction = opportunity_scores[headline]
    matched = sorted(opportunity_scores, key=lambda k: opportunity_scores[k], reverse=True)

    return ScoreResult(
        conviction=conviction,
        band=band_for(conviction).value,
        headline_opportunity=headline,
        opportunity_scores=opportunity_scores,
        matched_opportunity_types=matched,
        signal_ids=contributing.get(headline, []),
    )


async def rescore_site(db, uprn: str) -> ScoreResult:
    """Load a site's signals and score them. Used by synthesis and validation."""
    stmt = select(Signal).where(Signal.site_uprn == uprn)
    signals = list((await db.execute(stmt)).scalars().all())
    result = score_signals(signals)
    log.info(
        "site_rescored",
        uprn=uprn,
        conviction=result.conviction,
        band=result.band,
        headline=result.headline_opportunity,
    )
    return result
