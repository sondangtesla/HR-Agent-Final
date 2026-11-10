"""Short conversation memory and pending HR ticket drafts (K25).

Both live only in Redis, keyed by the employee_id from the bearer token, with a short TTL.
Nothing here reaches PostgreSQL or the trace. Callers store text that is already redacted.
"""
from __future__ import annotations

from typing import Any

from .cache import ResilientCache

HISTORY_MESSAGES = 6  # three user/assistant exchanges
TTL_SECONDS = 15 * 60
ROLES = frozenset({"user", "assistant"})
TICKET_CATEGORIES = frozenset({"policy_question", "leave_exception", "technical_issue", "privacy"})


class ConversationStore:
    def __init__(self, cache: ResilientCache, ttl_seconds: int = TTL_SECONDS) -> None:
        self.cache = cache
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _history_key(employee_id: str) -> str:
        return f"conv:v1:{employee_id}:history"

    @staticmethod
    def _draft_key(employee_id: str) -> str:
        return f"conv:v1:{employee_id}:ticket_draft"

    # --- History ---

    def history(self, employee_id: str) -> list[dict[str, str]]:
        """Last messages as Responses API input items. Anything malformed is dropped."""
        stored = self.cache.get(self._history_key(employee_id))
        if not isinstance(stored, list):
            return []
        return [
            {"role": item["role"], "content": item["content"]}
            for item in stored[-HISTORY_MESSAGES:]
            if isinstance(item, dict) and item.get("role") in ROLES and isinstance(item.get("content"), str)
        ]

    def remember(self, employee_id: str, user_text: str, assistant_text: str) -> None:
        messages = self.history(employee_id) + [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ]
        self.cache.set(self._history_key(employee_id), messages[-HISTORY_MESSAGES:], self.ttl_seconds)

    # --- Ticket draft ---

    def save_draft(self, employee_id: str, category: str, summary: str) -> bool:
        """False when the draft could not be stored: the caller must then not offer to send it."""
        return self.cache.set(
            self._draft_key(employee_id), {"category": category, "summary": summary}, self.ttl_seconds
        )

    def take_draft(self, employee_id: str) -> dict[str, str] | None:
        """Remove and return the draft atomically, so one draft becomes at most one ticket."""
        return self._valid_draft(self.cache.pop(self._draft_key(employee_id)))

    def discard_draft(self, employee_id: str) -> None:
        self.cache.delete(self._draft_key(employee_id))

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
