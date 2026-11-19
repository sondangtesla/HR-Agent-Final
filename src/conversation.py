"""Short conversation memory and pending HR ticket drafts.

Both live only in Redis with a short TTL. Nothing here reaches PostgreSQL or the trace, and
callers store text that is already redacted.

Everything is keyed by a scope: the employee_id from the bearer token plus the optional
conversation_id from the request. The conversation_id only separates one employee's own
conversations (the evaluator runs every case in a fresh one); it can never reach another
employee's memory, because the employee_id part always comes from the token.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .cache import ResilientCache

HISTORY_MESSAGES = 6  # three user/assistant exchanges
TTL_SECONDS = 15 * 60
ROLES = frozenset({"user", "assistant"})
TICKET_CATEGORIES = frozenset({"policy_question", "leave_exception", "technical_issue", "privacy"})


def conversation_scope(employee_id: str, conversation_id: str | None) -> str:
    """Hashed so client text never becomes part of a Redis key as-is."""
    conversation = hashlib.sha256((conversation_id or "default").encode("utf-8")).hexdigest()[:16]
    return f"{employee_id}:{conversation}"


class ConversationStore:
    def __init__(self, cache: ResilientCache, ttl_seconds: int = TTL_SECONDS) -> None:
        self.cache = cache
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _history_key(scope: str) -> str:
        return f"conv:v2:{scope}:history"

    @staticmethod
    def _draft_key(scope: str) -> str:
        return f"conv:v2:{scope}:ticket_draft"

    # --- History ---

    def history(self, scope: str) -> list[dict[str, str]]:
        """Last messages as Responses API input items. Anything malformed is dropped."""
        stored = self.cache.get(self._history_key(scope))
        if not isinstance(stored, list):
            return []
        return [
            {"role": item["role"], "content": item["content"]}
            for item in stored[-HISTORY_MESSAGES:]
            if isinstance(item, dict) and item.get("role") in ROLES and isinstance(item.get("content"), str)
        ]

    def remember(self, scope: str, user_text: str, assistant_text: str) -> None:
        messages = self.history(scope) + [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ]
        self.cache.set(self._history_key(scope), messages[-HISTORY_MESSAGES:], self.ttl_seconds)

    # --- Ticket draft ---

    def save_draft(self, scope: str, category: str, summary: str) -> bool:
        """False when the draft could not be stored: the caller must then not offer to send it."""
        return self.cache.set(self._draft_key(scope), {"category": category, "summary": summary}, self.ttl_seconds)

    def take_draft(self, scope: str) -> dict[str, str] | None:
        """Remove and return the draft atomically, so one draft becomes at most one ticket."""
        return self._valid_draft(self.cache.pop(self._draft_key(scope)))

    @staticmethod
    def _valid_draft(value: Any) -> dict[str, str] | None:
        if (
            isinstance(value, dict)
            and value.get("category") in TICKET_CATEGORIES
            and isinstance(value.get("summary"), str)
            and value["summary"].strip()
        ):
            return {"category": value["category"], "summary": value["summary"]}
        return None
