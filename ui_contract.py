"""Testable persona selection and API contract for the supplied Streamlit client."""

from __future__ import annotations

import json
import uuid
from pathlib import Path


API_PATHS = {
    "chat": "/api/v1/chat",
    "confirm": "/api/v1/action-proposals/{proposal_id}/confirm",
    "my_requests": "/api/v1/leave-requests/me",
    "monitoring_summary": "/api/v1/monitoring/summary",
    "monitoring_alerts": "/api/v1/monitoring/alerts",
}


def load_personas(path: Path) -> list[dict[str, str]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("A nonempty demo persona catalog is required.")
    for row in rows:
        if not isinstance(row, dict) or not all(
            isinstance(row.get(key), str) and row[key]
            for key in ("employee_id", "label", "scenario", "demo_token")
        ):
            raise ValueError("Invalid demo persona.")
    return rows


def _forget_chat(state: dict) -> None:
    """Drop the shown answer, the confirmation keys, and the conversation of the previous chat."""
    state.pop("last_chat", None)
    state.pop("conversation_id", None)
    for key in list(state):
        if key.startswith("idem_"):
            state.pop(key, None)


def select_persona(state: dict, persona: dict[str, str]) -> None:
    """Clear responses, confirmation keys, and the conversation when the active identity changes."""
    if state.get("active_employee_id") == persona["employee_id"]:
        return
    state["active_employee_id"] = persona["employee_id"]
    _forget_chat(state)


def current_conversation_id(state: dict) -> str:
    """One conversation per browser session (T2).

    The API keeps short memory and ticket drafts per (employee from the token, conversation_id),
    so a second browser tab of the same persona gets its own: a "ya" typed there can never send
    a draft made in the first tab.
    """
    if "conversation_id" not in state:
        state["conversation_id"] = uuid.uuid4().hex
    return state["conversation_id"]


def start_new_conversation(state: dict) -> None:
    """"Percakapan baru": the next message gets a new conversation_id. The old memory and any
    unsent ticket draft stay with the old one and expire there (15 minutes)."""
    _forget_chat(state)

