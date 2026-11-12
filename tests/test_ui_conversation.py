"""T2: the supplied UI sends one conversation_id per browser session."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.contracts import ChatRequest
from ui_contract import current_conversation_id, select_persona, start_new_conversation

APP = Path(__file__).resolve().parents[1] / "app.py"
CHAT_REPLY = {
    "answer": "Jawaban.", "outcome": "answered", "citations": [], "tool_calls": [],
    "action_proposal": None, "trace_id": "tr-test",
    "usage": {"input_tokens": 0, "output_tokens": 0, "latency_ms": 0, "estimated_cost": None},
}


# --- Pure helpers ---

def test_one_conversation_id_per_session_and_valid_for_the_api() -> None:
    state: dict = {}
    first = current_conversation_id(state)
    assert current_conversation_id(state) == first
    ChatRequest(message="halo", conversation_id=first)  # accepted by the API contract (max 100 chars)


def test_new_conversation_drops_the_old_chat_and_gets_a_new_id() -> None:
    state: dict = {"active_employee_id": "EMP-001", "last_chat": {"answer": "lama"}, "idem_AP-1": "key"}
    old = current_conversation_id(state)
    start_new_conversation(state)
    assert state == {"active_employee_id": "EMP-001"}
    assert current_conversation_id(state) != old


def test_persona_change_starts_a_new_conversation() -> None:
    state: dict = {"active_employee_id": "EMP-001"}
    old = current_conversation_id(state)
    select_persona(state, {"employee_id": "EMP-002"})
    assert current_conversation_id(state) != old


# --- The real Streamlit script, with the API call captured instead of sent ---

class _Reply:
    is_error = False

    def json(self) -> dict:
        return CHAT_REPLY


def test_supplied_ui_sends_the_conversation_id_and_renews_it_on_request() -> None:
    sent: list[dict] = []

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        sent.append(kwargs["json"])
        return _Reply()

    def send(app: AppTest, text: str) -> None:
        app.text_area[0].input(text).run()
        next(button for button in app.button if button.label == "Kirim").click().run()

    with patch("httpx.request", fake_request):
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        send(app, "Berapa saldo cuti saya?")
        send(app, "Dan aturan pengajuannya?")
        next(button for button in app.sidebar.button if button.label == "Percakapan baru").click().run()
        send(app, "Topik baru")

    assert [body["message"] for body in sent] == ["Berapa saldo cuti saya?", "Dan aturan pengajuannya?", "Topik baru"]
    first, second, third = (body["conversation_id"] for body in sent)
    assert first and first == second  # same browser session, same conversation
    assert third != first  # "Percakapan baru" starts another one
    assert not app.exception
