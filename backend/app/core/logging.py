"""Structured logging. GDPR: PII must never be logged (§3.3, §12)."""
from __future__ import annotations

import logging

import structlog

from app.core.config import settings

# Keys that must never appear in logs. Best-effort scrub at the processor level.
_PII_KEYS = {"name", "owner_name", "deceased_name", "email", "phone", "address", "dob"}


def _scrub_pii(_logger, _method, event_dict):
    for k in list(event_dict.keys()):
        if k.lower() in _PII_KEYS:
            event_dict[k] = "[redacted]"
    return event_dict


def configure_logging() -> None:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _scrub_pii,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "parallax"):
    return structlog.get_logger(name)
