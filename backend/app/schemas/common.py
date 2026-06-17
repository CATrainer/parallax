"""Standard response envelope (§8.1). Every endpoint returns these, never raw dicts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Meta(BaseModel):
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    from_cache: bool = False


class ErrorBody(BaseModel):
    code: str
    message: str  # human-readable; never leaks PII (§8.1)


class Ok(BaseModel, Generic[T]):
    ok: bool = True
    data: T
    meta: Meta = Field(default_factory=Meta)


class Err(BaseModel):
    ok: bool = False
    error: ErrorBody
    data: None = None


def ok(data: Any, from_cache: bool = False) -> dict:
    return {"ok": True, "data": data, "meta": Meta(from_cache=from_cache).model_dump(mode="json")}


def err(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message}, "data": None}
