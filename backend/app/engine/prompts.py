"""Prompt templates + strict-JSON output schemas for the synthesis tasks (§6.3).

The model is the *hero* but it is on a short leash. Guardrails are baked into every
system prompt: the model may only assert what the signals support; it phrases inference
as inference ("appears", "consistent with", "likely"), never as fact; it never invents
sources or values; missing data is a stated absence, never fabrication. Voice is an
analyst's — precise, hedged where honest, never salesy (§9.4).

Each task exposes:
  - a SYSTEM prompt (role + guardrails),
  - an OUTPUT_SCHEMA dict (the exact JSON shape we demand back),
  - a `build_user_*` helper that renders the compact payload into a user message.

`AnthropicProvider` includes the schema verbatim in the prompt so the model returns
strictly-shaped JSON; `synthesis.py` re-validates and repairs signal-id references
afterwards regardless of provider.
"""
from __future__ import annotations

import json
from typing import Any

# ─────────────────────────────────────── shared guardrails ───────────────────────────────────────
GUARDRAILS = (
    "You are a property-intelligence analyst writing a sourced briefing about a single UK site. "
    "A briefing is a synthesised inference, NOT a statement of fact. Strict rules you must never break:\n"
    "1. Assert only what the supplied signals support. Every claim must trace to one or more signal ids.\n"
    "2. Phrase inference as inference: use 'appears', 'consistent with', 'likely', 'suggests'. "
    "Never state an inference as established fact.\n"
    "3. Never invent sources, figures, dates, names, or values. Use only what is in the payload.\n"
    "4. Missing data is a stated absence ('no current listing was found'), never fabrication.\n"
    "5. Do not be salesy or breathless. Calm, precise, editorial. Sentence case. Active voice.\n"
    "6. Personal data is sensitive: refer to people by role where possible (an executor, the proprietor); "
    "do not speculate about individuals beyond what the signals evidence.\n"
    "7. Output STRICT JSON matching the provided schema exactly. No markdown, no commentary, no code fences."
)


def _schema_block(schema: dict[str, Any]) -> str:
    return (
        "Return ONLY a JSON object matching this schema exactly (types shown as hints):\n"
        + json.dumps(schema, indent=2)
    )


# ─────────────────────────────────── classify_signals (cheap) ───────────────────────────────────
CLASSIFY_SCHEMA: dict[str, Any] = {
    "clusters": [
        {
            "opportunity_type": "str — one opportunity type id this group of signals points to",
            "signal_ids": ["str — ids of the signals supporting this cluster"],
            "rationale": "str — one short hedged sentence on why these cohere",
            "confidence": "float 0.0-1.0",
        }
    ],
    "candidate": "bool — true if at least one cluster looks worth a full briefing",
    "summary": "str — one plain sentence describing the strongest pattern, hedged",
}

CLASSIFY_SYSTEM = (
    GUARDRAILS
    + "\n\nTASK: classify_signals. Cheaply group the supplied weak signals into opportunity "
    "clusters for breadth triage across a whole patch. Do NOT write prose narrative here — this is "
    "fast structured extraction. Only reference signal ids that appear in the payload."
)


# ────────────────────────────────── synthesize_briefing (premium) ──────────────────────────────────
BRIEFING_SCHEMA: dict[str, Any] = {
    "lede": "str — one-sentence plain-English conclusion, hedged, no signal ids in the text",
    "paragraphs": [
        {
            "text": "str — a reasoning paragraph; cite evidence in prose, not by id",
            "cited_signal_ids": ["str — ids of signals this paragraph relies on"],
        }
    ],
    "takeaway": "str — one sentence on why this is actionable for a deal sourcer",
    "conclusions": [
        {
            "type": "str — a manufactured-conclusion type, e.g. 'probable_motivation', "
            "'disposal_route', 'wrong_use'",
            "statement": "str — the inferred conclusion, phrased as inference",
            "confidence": "float 0.0-1.0",
            "contributing_signal_ids": ["str — ids of contributing signals"],
        }
    ],
    "opportunity_types": ["str — opportunity type ids this site matches"],
}

BRIEFING_SYSTEM = (
    GUARDRAILS
    + "\n\nTASK: synthesize_briefing. Fuse the signal bundle into the briefing narrative and "
    "manufacture conclusions (probable motivation, likely disposal route, wrong-use detection) that "
    "exist in no single database — these are the asset, but they must be reasoned strictly from the "
    "signals.\n\n"
    "Structure: a one-sentence lede; 2-3 reasoning paragraphs, each citing the signal ids it used; a "
    "one-sentence takeaway on actionability; and 1-4 manufactured conclusions with confidences derived "
    "from how strongly the contributing signals corroborate.\n"
    "Conviction comes from CORROBORATION across independent sources — say so when several sources agree, "
    "and widen your hedge when only one does. The numeric conviction and band are computed separately and "
    "supplied to you for context; your job is to EXPLAIN that level, never to invent a different number. "
    "Every cited_signal_ids / contributing_signal_ids value MUST be an id present in the payload."
)


# ─────────────────────────────────── broker_situation (cheap) ───────────────────────────────────
BROKER_SCHEMA: dict[str, Any] = {
    "owner_situation": "str — one or two hedged sentences on the owner's likely situation",
    "mortgage_event_likelihood": "int 0-100 — likelihood of an imminent mortgage event",
    "drivers": ["str — short phrases naming the signals driving the inference"],
    "transaction_likelihood": "int 0-100 — likelihood the owner transacts on the property",
    "rationale": "str — one hedged sentence justifying the likelihood",
}

BROKER_SYSTEM = (
    GUARDRAILS
    + "\n\nTASK: broker_situation. Through the broker lens, infer whether the owner's situation implies "
    "an imminent mortgage event (moving, remortgage off a fixed rate, BTL purchase, inherited-and-keeping). "
    "This is intelligence on a person likely to transact, not a property pitch. Hedge appropriately and "
    "drive every driver phrase from a real signal in the payload."
)


# ─────────────────────────────────────────── registry ───────────────────────────────────────────
TASK_SCHEMAS: dict[str, dict[str, Any]] = {
    "classify_signals": CLASSIFY_SCHEMA,
    "synthesize_briefing": BRIEFING_SCHEMA,
    "broker_situation": BROKER_SCHEMA,
}

TASK_SYSTEMS: dict[str, str] = {
    "classify_signals": CLASSIFY_SYSTEM,
    "synthesize_briefing": BRIEFING_SYSTEM,
    "broker_situation": BROKER_SYSTEM,
}


# ──────────────────────────────────────── user messages ─────────────────────────────────────────
def build_user_message(task: str, payload: dict[str, Any]) -> str:
    """Render the compact payload + the demanded schema into a single user message."""
    schema = TASK_SCHEMAS.get(task, {})
    payload_json = json.dumps(payload, indent=2, default=str)
    intro = {
        "classify_signals": "Classify these signals for a single site:",
        "synthesize_briefing": "Write the briefing for this site from its signal bundle:",
        "broker_situation": "Assess the owner's transaction situation for this site:",
    }.get(task, "Process this payload:")
    return f"{intro}\n\n{payload_json}\n\n{_schema_block(schema)}"
