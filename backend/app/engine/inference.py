"""Provider-agnostic AI abstraction (§6.3).

Every synthesis task is routed through `InferenceProvider.complete(task, payload) -> dict`.
Tasks: "classify_signals" (cheap), "synthesize_briefing" (premium), "broker_situation" (cheap).

Two implementations:
  - `AnthropicProvider` — uses the `anthropic` AsyncAnthropic SDK; builds system+user messages
    per task, demands strict JSON, parses robustly. Raises on any error so the caller falls back.
  - `TemplateProvider` — NO network. Deterministically renders the SAME JSON shape from the payload
    using string templates, producing a genuinely readable, sourced, analyst-style briefing. This is
    the offline fallback and MUST always succeed. The app runs fully with no Anthropic key.

`get_provider(tier)` routes via settings: template mode or no key → TemplateProvider, else Anthropic.
"""
from __future__ import annotations

import json
import re
from typing import Any, Literal, Protocol, runtime_checkable

from app.core.config import settings
from app.core.logging import get_logger
from app.engine import prompts

log = get_logger("parallax.inference")


# ─────────────────────────────────────────── protocol ───────────────────────────────────────────
@runtime_checkable
class InferenceProvider(Protocol):
    name: str

    async def complete(self, task: str, payload: dict) -> dict:
        """Run `task` over `payload`, returning a dict matching the task's output schema."""
        ...


# ───────────────────────────────────── JSON extraction helper ─────────────────────────────────────
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _extract_json(text: str) -> dict[str, Any]:
    """Robustly pull a JSON object out of a model response (strip code fences, find the object)."""
    if not text:
        raise ValueError("empty model response")
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced {...} span.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(cleaned[start : end + 1])
    raise ValueError("no JSON object found in model response")


# ───────────────────────────────────────── Anthropic ─────────────────────────────────────────────
class AnthropicProvider:
    """Hits the Anthropic API. Model chosen by tier in the constructor. Raises on any failure."""

    def __init__(self, tier: Literal["cheap", "premium"] = "premium") -> None:
        self.tier = tier
        self.model = (
            settings.anthropic_model_cheap if tier == "cheap" else settings.anthropic_model_premium
        )
        self.name = f"anthropic/{self.model}"

    async def complete(self, task: str, payload: dict) -> dict:
        system = prompts.TASK_SYSTEMS.get(task)
        if system is None:
            raise ValueError(f"unknown inference task: {task}")
        user = prompts.build_user_message(task, payload)

        # Imported lazily so the SDK is only required when actually used.
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        try:
            resp = await client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # surface so the caller can fall back to the template
            log.warning("anthropic_complete_failed", task=task, tier=self.tier, error=str(exc))
            raise

        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        try:
            data = _extract_json(text)
        except (ValueError, json.JSONDecodeError) as exc:
            log.warning("anthropic_parse_failed", task=task, error=str(exc))
            raise
        if not isinstance(data, dict):
            raise ValueError("model returned non-object JSON")
        return data


# ───────────────────────────────────────── Template ──────────────────────────────────────────────
# Human-readable phrasing per signal type. Each entry yields an inference-phrased clause.
_SIGNAL_PHRASING: dict[str, str] = {
    "probate_inherited": "a deceased-estate notice appears to match this address, consistent with the "
    "property having been inherited",
    "epc_lapsed": "the energy certificate has lapsed without renewal, which is consistent with the "
    "home sitting unoccupied",
    "epc_fg_refurb": "the property holds an F/G energy rating, suggesting tired stock in need of "
    "refurbishment",
    "no_listing": "no current sale listing was found through sanctioned sources, so any disposal would "
    "not yet be on the open market",
    "owner_spv_distress": "the owning company shows signs of financial distress (late filings, charges "
    "or insolvency markers), consistent with motivation to release the asset",
    "long_hold_unimproved": "the site has been held for a long period without recorded improvement, "
    "consistent with an owner who cannot or will not modernise",
    "planning_refusal": "a planning application here was refused, which suggests the owner has already "
    "tried and failed to extract value",
    "commercial_empty": "rating records are consistent with the commercial unit standing empty",
    "wrong_use_gap": "the current use appears to sit below the site's latent higher-value potential",
    "site_activity_decline": "observed site activity appears to be declining over time",
    "long_distance_owner": "the registered owner's address appears far from the site, consistent with "
    "an absentee owner",
    "portfolio_regulatory_pressure": "the owner's portfolio appears exposed to regulatory pressure "
    "(MEES / tax), consistent with a tired-landlord exit",
    "single_property_owner": "the owner appears to hold no other property, which corroborates a "
    "one-off disposal rather than portfolio management",
}

# Maps a signal type to the manufactured-conclusion type it most supports.
_CONCLUSION_FOR_SIGNAL: dict[str, str] = {
    "probate_inherited": "probable_motivation",
    "owner_spv_distress": "probable_motivation",
    "long_distance_owner": "probable_motivation",
    "portfolio_regulatory_pressure": "probable_motivation",
    "planning_refusal": "probable_motivation",
    "no_listing": "disposal_route",
    "epc_lapsed": "occupancy",
    "commercial_empty": "occupancy",
    "wrong_use_gap": "wrong_use",
    "site_activity_decline": "wrong_use",
    "epc_fg_refurb": "condition",
    "long_hold_unimproved": "condition",
    "single_property_owner": "disposal_route",
}

_OPPORTUNITY_LABELS: dict[str, str] = {
    "empty_vacant": "an empty/vacant home",
    "probate_inherited": "an inherited property heading for disposal",
    "distressed_financial": "a financially distressed owner",
    "distressed_life": "an owner facing a life-event move",
    "below_market_tired": "tired, below-market stock",
    "development_planning": "a thwarted development site",
    "tired_landlord": "a tired landlord likely to exit",
    "wrong_use_commercial": "a commercial site in the wrong use",
}


def _confidence_label(c: float) -> str:
    if c >= 0.75:
        return "strongly"
    if c >= 0.5:
        return "moderately"
    return "tentatively"


class TemplateProvider:
    """Deterministic, no-network fallback. Always succeeds. Produces the same JSON shapes."""

    name = "template/deterministic-v1"

    async def complete(self, task: str, payload: dict) -> dict:
        if task == "classify_signals":
            return self._classify(payload)
        if task == "synthesize_briefing":
            return self._briefing(payload)
        if task == "broker_situation":
            return self._broker(payload)
        raise ValueError(f"unknown inference task: {task}")

    # ---- helpers over the payload -----------------------------------------------------------
    @staticmethod
    def _signals(payload: dict) -> list[dict]:
        return [s for s in payload.get("signals", []) if s.get("fired", True)]

    @staticmethod
    def _phrase(sig: dict) -> str:
        return _SIGNAL_PHRASING.get(
            sig.get("signal_type", ""),
            f"a {sig.get('signal_type', 'signal').replace('_', ' ')} signal was observed",
        )

    @staticmethod
    def _source_of(sig: dict) -> str:
        return sig.get("source") or "public records"

    # ---- classify_signals --------------------------------------------------------------------
    def _classify(self, payload: dict) -> dict:
        sigs = self._signals(payload)
        opp_scores: dict[str, float] = payload.get("opportunity_scores", {}) or {}
        clusters: list[dict] = []
        # Group fired signals by the opportunity their conclusion-type leans toward.
        by_opp: dict[str, list[dict]] = {}
        matched = payload.get("matched_opportunity_types") or list(opp_scores.keys())
        for opp in matched:
            members = [
                s
                for s in sigs
                if opp in (payload.get("signal_opportunity_map", {}).get(s.get("id"), [opp]))
            ]
            members = members or sigs  # degrade: attribute all fired signals if no explicit map
            if not members:
                continue
            conf = min(0.95, round(sum(s.get("strength", 0.5) for s in members) / max(len(members), 1), 2))
            by_opp[opp] = members
            clusters.append(
                {
                    "opportunity_type": opp,
                    "signal_ids": [s["id"] for s in members],
                    "rationale": f"these signals are consistent with {_OPPORTUNITY_LABELS.get(opp, opp)}",
                    "confidence": conf,
                }
            )
        strongest = (
            max(clusters, key=lambda c: c["confidence"])["opportunity_type"] if clusters else None
        )
        summary = (
            f"The signals on this site are most consistent with {_OPPORTUNITY_LABELS.get(strongest, strongest)}."
            if strongest
            else "No fired signals were found for this site."
        )
        return {
            "clusters": clusters,
            "candidate": bool(clusters),
            "summary": summary,
        }

    # ---- synthesize_briefing -----------------------------------------------------------------
    def _briefing(self, payload: dict) -> dict:
        site = payload.get("site", {})
        sigs = self._signals(payload)
        conviction = int(payload.get("conviction", 0))
        headline = payload.get("headline_opportunity")
        opp_types = payload.get("matched_opportunity_types") or (
            [headline] if headline else []
        )
        address = site.get("address", "this site")
        n_sources = len({self._source_of(s) for s in sigs})

        # --- lede ---
        if headline:
            lede = (
                f"{address} appears to be {_OPPORTUNITY_LABELS.get(headline, headline)}, "
                f"inferred from {len(sigs)} corroborating signal{'s' if len(sigs) != 1 else ''} "
                f"across {n_sources} independent source{'s' if n_sources != 1 else ''}."
            )
        elif sigs:
            lede = (
                f"{address} shows weak indications worth monitoring, drawn from "
                f"{len(sigs)} signal{'s' if len(sigs) != 1 else ''}, though no single opportunity yet dominates."
            )
        else:
            lede = (
                f"No fired signals are currently associated with {address}; this briefing notes the "
                f"absence rather than an opportunity."
            )

        # --- paragraphs (each cites the signal ids it leans on) ---
        paragraphs: list[dict] = []
        if sigs:
            # Para 1 — the evidence in plain reasoning.
            clauses = []
            for s in sigs[:4]:
                clauses.append(f"{self._phrase(s)} ({self._source_of(s)})")
            evidence_text = (
                "On the evidence available, " + "; ".join(clauses) + "."
            )
            paragraphs.append(
                {"text": evidence_text, "cited_signal_ids": [s["id"] for s in sigs[:4]]}
            )

            # Para 2 — corroboration / conviction reasoning.
            if n_sources >= 3:
                corr = (
                    f"These point the same way across {n_sources} independent sources, which is what "
                    f"lifts this from a flagged candidate toward a lead-grade reading; the conviction of "
                    f"{conviction} reflects that corroboration."
                )
            elif n_sources == 2:
                corr = (
                    f"Two independent sources agree here, which supports the inference but leaves room "
                    f"for doubt; the conviction of {conviction} is held back accordingly."
                )
            else:
                corr = (
                    f"This rests on a single source, so it is treated as a candidate rather than a lead; "
                    f"the conviction of {conviction} reflects that thin corroboration and the confidence "
                    f"interval is wide."
                )
            paragraphs.append({"text": corr, "cited_signal_ids": [s["id"] for s in sigs]})

            # Para 3 — ownership colour, only when we have it.
            ownership = payload.get("ownership", [])
            if ownership:
                o = ownership[0]
                role = o.get("role", "owner")
                conf = o.get("link_confidence", 0.0)
                otype = o.get("owner_type", "owner")
                who = "a company" if otype == "company" else "an individual"
                paragraphs.append(
                    {
                        "text": (
                            f"Ownership resolves to {who} in the role of {role} "
                            f"(link confidence {conf:.2f}); this is a probabilistic match rather than a "
                            f"confirmed title, and would be settled by validation."
                        ),
                        "cited_signal_ids": [],
                    }
                )

        # --- takeaway ---
        if sigs:
            takeaway = (
                "Worth a closer look: the combination here is the kind a sourcer could act on before it "
                "reaches the open market — validate ownership and occupancy before approaching."
                if conviction >= 56
                else "Keep on watch: the signal is real but thin; a second corroborating source would "
                "make this actionable."
            )
        else:
            takeaway = "Nothing to act on yet; revisit if new signals fire."

        # --- conclusions (manufactured; confidence from contributing signal strength) ---
        conclusions: list[dict] = []
        grouped: dict[str, list[dict]] = {}
        for s in sigs:
            ctype = _CONCLUSION_FOR_SIGNAL.get(s.get("signal_type", ""), "probable_motivation")
            grouped.setdefault(ctype, []).append(s)
        for ctype, members in grouped.items():
            conf = min(0.95, round(sum(m.get("strength", 0.5) for m in members) / len(members), 2))
            lead = members[0]
            statement = self._conclusion_statement(ctype, lead, conf, n_sources)
            conclusions.append(
                {
                    "type": ctype,
                    "statement": statement,
                    "confidence": conf,
                    "contributing_signal_ids": [m["id"] for m in members],
                }
            )

        return {
            "lede": lede,
            "paragraphs": paragraphs,
            "takeaway": takeaway,
            "conclusions": conclusions,
            "opportunity_types": [o for o in opp_types if o],
        }

    @staticmethod
    def _conclusion_statement(ctype: str, lead: dict, conf: float, n_sources: int) -> str:
        adv = _confidence_label(conf)
        templates = {
            "probable_motivation": f"The owner is {adv} likely to be motivated to sell — "
            + TemplateProvider._phrase(lead)
            + ".",
            "disposal_route": f"Any disposal would {adv} appear to be off-market for now — "
            + TemplateProvider._phrase(lead)
            + ".",
            "occupancy": f"The property {adv} appears to be unoccupied — "
            + TemplateProvider._phrase(lead)
            + ".",
            "wrong_use": f"The current use {adv} appears to undershoot the site's potential — "
            + TemplateProvider._phrase(lead)
            + ".",
            "condition": f"The stock {adv} appears tired and improvable — "
            + TemplateProvider._phrase(lead)
            + ".",
        }
        return templates.get(ctype, f"An inference ({ctype}) is {adv} supported by the signals.")

    # ---- broker_situation --------------------------------------------------------------------
    def _broker(self, payload: dict) -> dict:
        sigs = self._signals(payload)
        conviction = int(payload.get("conviction", 0))
        drivers = [s.get("signal_type", "").replace("_", " ") for s in sigs[:4] if s.get("signal_type")]
        if sigs:
            situation = (
                "The owner's situation appears consistent with an approaching transaction or financing "
                f"event, drawn from {len(sigs)} signal{'s' if len(sigs) != 1 else ''}."
            )
            rationale = (
                "Likelihood reflects the corroboration across sources; treat as a hedged inference, not a "
                "confirmed event."
            )
        else:
            situation = "No signals currently indicate an imminent mortgage or transaction event."
            rationale = "Nothing in the available data points to a near-term event."
        return {
            "owner_situation": situation,
            "mortgage_event_likelihood": conviction,
            "drivers": drivers,
            "transaction_likelihood": conviction,
            "rationale": rationale,
        }


# ─────────────────────────────────────────── routing ─────────────────────────────────────────────
def get_provider(tier: Literal["cheap", "premium"]) -> InferenceProvider:
    """Route to a provider per settings. Template when forced or when no Anthropic key (§6.3)."""
    if settings.inference_provider == "template" or not settings.has_anthropic:
        return TemplateProvider()
    return AnthropicProvider(tier)
