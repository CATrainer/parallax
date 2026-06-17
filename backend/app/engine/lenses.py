"""L6 — Lenses & the opportunity taxonomy (§7).

Lenses are saved filters/views over the one opportunity graph — presentation, not
engine. The taxonomy is the anti-brittleness core: every opportunity is a *bundle*
of signals, never a single one. The first seven types run on the free Tier-1 spine;
``wrong_use_commercial`` leans on Tier-3 (imagery/footfall) and activates once cheap
lenses fund the imagery spend (§7.1).

This module is pure data + pure functions — import-safe, no DB, no network.
"""
from __future__ import annotations

from app.engine.signals import SIGNAL_CATALOGUE, decay_factor
from app.models.enums import SignalType

# ───────────────────────────────── Opportunity taxonomy (§7.1) ─────────────────────────────────
# Each entry:
#   label          — human-readable name
#   required_any   — at least one of these signal types must fire to consider the bundle
#   required_all   — every one of these must fire (usually empty; bundles are loose by design)
#   weights        — per-signal contribution to the 0–1 blend (need not sum to 1; normalised)
#   why_transacts  — the manufactured "why the owner moves" conclusion this lens reasons toward
#
# Weights are tuned so the *defining* signal of a bundle dominates while corroborators
# add conviction. Graceful degradation falls straight out of the weighted blend: a missing
# signal simply contributes nothing (§6.4).
OPPORTUNITY_TAXONOMY: dict[str, dict] = {
    "empty_vacant": {
        "label": "Empty / vacant (residential)",
        "required_any": [
            SignalType.epc_lapsed.value,
            SignalType.no_listing.value,
            SignalType.probate_inherited.value,
            SignalType.long_distance_owner.value,
        ],
        "required_all": [],
        "weights": {
            SignalType.epc_lapsed.value: 0.35,
            SignalType.no_listing.value: 0.15,
            SignalType.probate_inherited.value: 0.25,
            SignalType.long_distance_owner.value: 0.25,
        },
        "why_transacts": "Carrying cost with no income — an empty home bleeds money until it sells.",
    },
    "probate_inherited": {
        "label": "Probate / inherited",
        "required_any": [SignalType.probate_inherited.value],
        "required_all": [],
        "weights": {
            SignalType.probate_inherited.value: 0.6,
            SignalType.single_property_owner.value: 0.2,
            SignalType.epc_lapsed.value: 0.2,
        },
        "why_transacts": "Heirs liquidate rather than manage — an inherited home is rarely kept.",
    },
    "distressed_financial": {
        "label": "Distressed owner (financial)",
        "required_any": [SignalType.owner_spv_distress.value],
        "required_all": [],
        "weights": {
            SignalType.owner_spv_distress.value: 0.65,
            SignalType.single_property_owner.value: 0.15,
            SignalType.long_hold_unimproved.value: 0.2,
        },
        "why_transacts": "Financial pressure on the holding entity forces or motivates a sale.",
    },
    "distressed_life": {
        "label": "Distressed owner (life event)",
        "required_any": [
            SignalType.long_distance_owner.value,
            SignalType.probate_inherited.value,
        ],
        "required_all": [],
        "weights": {
            SignalType.long_distance_owner.value: 0.5,
            SignalType.probate_inherited.value: 0.3,
            SignalType.epc_lapsed.value: 0.2,
        },
        "why_transacts": "A life event — age, distance, bereavement — forces a move the owner did not plan.",
    },
    "below_market_tired": {
        "label": "Below-market / tired stock",
        "required_any": [
            SignalType.long_hold_unimproved.value,
            SignalType.epc_fg_refurb.value,
        ],
        "required_all": [],
        "weights": {
            SignalType.long_hold_unimproved.value: 0.45,
            SignalType.epc_fg_refurb.value: 0.4,
            SignalType.epc_lapsed.value: 0.15,
        },
        "why_transacts": "Long hold, no improvement — an owner who can't or won't modernise.",
    },
    "development_planning": {
        "label": "Development / planning",
        "required_any": [SignalType.planning_refusal.value],
        "required_all": [],
        "weights": {
            SignalType.planning_refusal.value: 0.7,
            SignalType.long_hold_unimproved.value: 0.3,
        },
        "why_transacts": "Tried and failed to extract value through planning — motivated to exit.",
    },
    "tired_landlord": {
        "label": "Tired landlord / portfolio exit",
        "required_any": [SignalType.portfolio_regulatory_pressure.value],
        "required_all": [],
        "weights": {
            SignalType.portfolio_regulatory_pressure.value: 0.55,
            SignalType.epc_fg_refurb.value: 0.25,
            SignalType.owner_spv_distress.value: 0.2,
        },
        "why_transacts": "Regulatory burden (MEES / S24) tips a tired landlord toward exiting.",
    },
    # The off-centroid Tier-3 bet — accepted by the engine, gated on imagery spend (§7.1).
    "wrong_use_commercial": {
        "label": "Wrong-use commercial",
        "required_any": [
            SignalType.commercial_empty.value,
            SignalType.wrong_use_gap.value,
            SignalType.site_activity_decline.value,
        ],
        "required_all": [],
        "weights": {
            SignalType.commercial_empty.value: 0.35,
            SignalType.site_activity_decline.value: 0.3,
            SignalType.wrong_use_gap.value: 0.25,
            SignalType.planning_refusal.value: 0.1,
        },
        "why_transacts": "Current use is failing while a higher use sits latent — value waiting to be unlocked.",
    },
}


def _present_by_type(signals) -> dict[str, list]:
    """Group fired signals by signal_type value. Non-fired (checked-not-firing) are excluded."""
    by_type: dict[str, list] = {}
    for s in signals:
        if not getattr(s, "fired", True):
            continue
        by_type.setdefault(s.signal_type, []).append(s)
    return by_type


def opportunities_for(signals) -> list[tuple[str, float]]:
    """Score every opportunity type over the present signal bundle.

    Returns ``(opportunity_type, score 0-1)`` sorted high→low, excluding bundles whose
    ``required_any`` gate is unmet (score would be a non-signal). Pure: no DB, no decay-time
    coupling beyond ``observed_at`` already on each signal.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    by_type = _present_by_type(signals)
    results: list[tuple[str, float]] = []

    for opp_type, spec in OPPORTUNITY_TAXONOMY.items():
        present = {t for t in spec["weights"] if t in by_type}

        # Gate: required_any (at least one) and required_all (every one).
        required_any = spec.get("required_any") or []
        if required_any and not (present & set(required_any)):
            continue
        required_all = spec.get("required_all") or []
        if required_all and not set(required_all).issubset(present):
            continue

        weights: dict[str, float] = spec["weights"]
        total_weight = sum(weights.values()) or 1.0
        accrued = 0.0
        for sig_type, weight in weights.items():
            sigs = by_type.get(sig_type)
            if not sigs:
                continue
            # Best contributing signal of this type wins (strongest, freshest).
            best = 0.0
            for s in sigs:
                strength = float(getattr(s, "strength", 0.0) or 0.0)
                decays = getattr(s, "decays", "slow") or "slow"
                observed = getattr(s, "observed_at", None)
                d = decay_factor(decays, observed, now)
                best = max(best, strength * d)
            accrued += weight * best
        score = max(0.0, min(1.0, accrued / total_weight))
        if score > 0:
            results.append((opp_type, score))

    results.sort(key=lambda t: t[1], reverse=True)
    return results


# ───────────────────────────────── Product lenses (presentation) ────────────────────────────────
# The three Product-1 rungs/surfaces + the broker lens. These are *presentation* filters only —
# default views over the same opportunity graph (§7.2, §11). They do not touch scoring.
LENSES: dict = {
    "single_site_deep_dive": {
        "label": "Single-site deep-dive",
        "rung": "entry",
        "surface": "pull",
        "filters": {
            "opportunity_types": list(OPPORTUNITY_TAXONOMY.keys()),
            "min_conviction": 0,
        },
    },
    "area_search": {
        "label": "Area search",
        "rung": "entry",
        "surface": "pull",
        "filters": {
            "opportunity_types": list(OPPORTUNITY_TAXONOMY.keys()),
            "min_conviction": 0,
        },
    },
    "patch_coverage": {
        "label": "Patch coverage",
        "rung": "sourcer",
        "surface": "push",
        "filters": {
            # Residential spine — the first seven, surfaced above the patch floor.
            "opportunity_types": [
                k for k in OPPORTUNITY_TAXONOMY if k != "wrong_use_commercial"
            ],
            "min_conviction": 31,  # MONITOR floor (§6.4)
        },
    },
    "broker": {
        "label": "Broker console",
        "rung": "broker",
        "surface": "enrich",
        "filters": {
            # Owner-situation lenses: transaction-likelihood, not property finding (§11).
            "opportunity_types": [
                "probate_inherited",
                "distressed_financial",
                "distressed_life",
                "tired_landlord",
            ],
            "min_conviction": 0,
        },
    },
}
