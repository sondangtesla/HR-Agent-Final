"""Security helpers. Complete every TODO before persisting telemetry."""
from __future__ import annotations

import hashlib


def token_hash(token: str) -> str:
    """Return a deterministic SHA-256 hex digest so the raw token is never stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def stable_safety_id(employee_id: str) -> str:
    # TODO(M2): Return a stable, non-identifying hash suitable for provider safety_identifier.
    raise NotImplementedError


def redact(value: str) -> str:
    # TODO(M2): Redact email, Indonesian phone numbers, token-like values, and medical detail.
    raise NotImplementedError

