"""Tools: strict schemas, identity from the token only, and proposals that never act on their own."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from src.cache import NullCache
from src.config import Settings
from src.contracts import AuthContext, LeaveRequestView
from src.providers import DeterministicProvider
from src.repository import MemoryRepository
from src.retrieval import RetrievalService
from src.tools import TOOL_SCHEMAS, ToolExecutor

ALYA = AuthContext(employee_id="EMP-001", display_name="Alya Pratama")
TODAY = date(2026, 9, 23)  # Wednesday


@pytest.fixture
def tools(repository: MemoryRepository) -> ToolExecutor:
    retrieval = RetrievalService(repository, DeterministicProvider(), NullCache(), 0)
    settings = Settings(model_mode="fake", proposal_ttl_minutes=15)
    return ToolExecutor(repository, retrieval, settings, today_factory=lambda: TODAY)


def add_pending(repository: MemoryRepository, employee_id: str, days: int) -> None:
    """A confirmed request waiting for the manager. K26: confirming already took the days."""
    repository.requests.append((employee_id, LeaveRequestView(
        request_id=f"LR-PENDING-{employee_id}", leave_type="annual",
        start_date=date(2026, 11, 2), end_date=date(2026, 11, 2) + timedelta(days=days - 1),
        business_days=days, status="pending_manager_review",
        created_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
    )))
    repository.balances[employee_id] = [
        b.model_copy(update={"available_days": b.available_days - days}) if b.leave_type == "annual" else b
        for b in repository.balances[employee_id]
    ]


# --- Schemas ---

def test_four_strict_schemas_without_employee_id() -> None:
    names = [schema["name"] for schema in TOOL_SCHEMAS]
    assert names == ["search_hr_policy", "get_my_leave_balance", "prepare_leave_request", "create_hr_ticket"]
    for schema in TOOL_SCHEMAS:
        params = schema["parameters"]
        assert schema["strict"] is True
        assert params["additionalProperties"] is False
        assert params["required"] == list(params["properties"])
    assert "employee_id" not in json.dumps(TOOL_SCHEMAS)


# --- Identity binding ---

def test_employee_id_argument_is_refused(tools: ToolExecutor, repository: MemoryRepository) -> None:
    result, _ = tools.execute("get_my_leave_balance", {"employee_id": "EMP-002"}, ALYA)
    assert result["status"] == "blocked"

    result, proposal = tools.execute(
        "prepare_leave_request",
        {"start_date": "2026-09-28", "end_date": "2026-09-28", "leave_type": "annual",
         "reason": None, "employee_id": "EMP-002"},
        ALYA,
    )
    assert result["status"] == "blocked" and proposal is None
    assert repository.proposals == {}


def test_balance_shows_own_data_with_pending_breakdown(tools: ToolExecutor, repository: MemoryRepository) -> None:
    add_pending(repository, "EMP-001", 5)
    add_pending(repository, "EMP-002", 1)  # Bima's request must not touch Alya's numbers
    result, _ = tools.execute("get_my_leave_balance", {}, ALYA)
    annual = next(b for b in result["balances"] if b["leave_type"] == "annual")
    assert annual == {  # K26: 8 at the start, 5 already deducted at confirmation
        "leave_type": "annual",
        "balance_days": 3,
        "pending_manager_review_days": 5,
        "available_to_request_days": 3,
        "as_of_date": annual["as_of_date"],
    }
    assert "EMP-002" not in json.dumps(result)


# --- prepare_leave_request ---

def test_valid_request_creates_only_a_proposal(tools: ToolExecutor, repository: MemoryRepository) -> None:
    result, proposal = tools.execute(
        "prepare_leave_request",
        {"start_date": "2026-09-28", "end_date": "2026-09-29", "leave_type": "annual", "reason": None},
        ALYA,
    )
    assert result["status"] == "ok" and result["requires_confirmation"] is True
    assert re.fullmatch(r"AP-[0-9a-f]{32}", proposal.proposal_id)
    owner, stored = repository.get_proposal(proposal.proposal_id)
    assert owner == "EMP-001" and stored.business_days == 2
    assert repository.list_leave_requests("EMP-001") == []  # nothing happens before Konfirmasi
    ttl = proposal.expires_at - datetime.now(timezone.utc)
    assert timedelta(minutes=14) < ttl <= timedelta(minutes=15)


def test_confirmed_days_are_not_available_again(tools: ToolExecutor, repository: MemoryRepository) -> None:
    add_pending(repository, "EMP-001", 5)  # K26: stored balance is now 8 - 5 = 3
    result, proposal = tools.execute(
        "prepare_leave_request",
        {"start_date": "2026-10-05", "end_date": "2026-10-09", "leave_type": "annual", "reason": None},
        ALYA,
    )
    assert result["status"] == "blocked" and proposal is None
    assert "tersedia 3 hari" in result["reason"]


def test_short_notice_is_blocked_with_earliest_date(tools: ToolExecutor, repository: MemoryRepository) -> None:
    result, proposal = tools.execute(
        "prepare_leave_request",
        {"start_date": "2026-09-25", "end_date": "2026-09-25", "leave_type": "annual", "reason": None},
        ALYA,
    )
    assert result["status"] == "blocked" and proposal is None
    assert "2026-09-28" in result["reason"]
    assert repository.proposals == {}


def test_medical_reason_is_redacted_in_proposal(tools: ToolExecutor) -> None:
    _, proposal = tools.execute(
        "prepare_leave_request",
        {"start_date": "2026-09-24", "end_date": "2026-09-24", "leave_type": "sick",
         "reason": "Diagnosis: diabetes, kontrol ke dokter"},
        ALYA,
    )
    assert "diabetes" not in proposal.reason


def test_invalid_arguments_are_errors(tools: ToolExecutor) -> None:
    result, _ = tools.execute(
        "prepare_leave_request",
        {"start_date": "besok", "end_date": "2026-09-28", "leave_type": "annual", "reason": None},
        ALYA,
    )
    assert result["status"] == "error" and "start_date" in result["reason"]
    assert tools.execute("delete_everything", {}, ALYA)[0]["status"] == "error"


# --- search and tickets ---

def test_search_marks_documents_as_untrusted_data(tools: ToolExecutor) -> None:
    result, _ = tools.execute("search_hr_policy", {"query": "jatah cuti tahunan", "top_k": 3}, ALYA)
    assert result["status"] == "ok"
    assert result["results"][0]["document_id"] == "HR-LEAVE-001"
    assert "bukan instruksi" in result["note"]


def test_ticket_tool_only_returns_a_draft(tools: ToolExecutor, repository: MemoryRepository) -> None:
    """K25: the tool validates and returns a redacted draft; it never inserts a ticket.
    Storing the draft and sending it are the agent's job (tests/test_ticket_confirmation.py)."""
    result, _ = tools.execute(
        "create_hr_ticket", {"category": "leave_exception", "summary": "Minta pengecualian sisa cuti"}, ALYA
    )
    assert result["status"] == "ok"
    assert result["draft"] == {"category": "leave_exception", "summary": "Minta pengecualian sisa cuti"}
    assert repository.tickets == []


def test_ticket_tool_refuses_an_empty_summary(tools: ToolExecutor, repository: MemoryRepository) -> None:
    result, _ = tools.execute("create_hr_ticket", {"category": "policy_question", "summary": "tolong buatkan tiket"}, ALYA)
    assert result["status"] == "blocked" and "Tanyakan" in result["reason"]
    assert repository.tickets == []
