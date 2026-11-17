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

def test_five_strict_schemas_without_employee_id() -> None:
    names = [schema["name"] for schema in TOOL_SCHEMAS]
    assert names == ["search_hr_policy", "get_my_leave_balance", "prepare_leave_request", "create_hr_ticket",
                     "get_team_leave_analytics"]
    for schema in TOOL_SCHEMAS:
        params = schema["parameters"]
        assert schema["strict"] is True
        assert params["additionalProperties"] is False
        assert params["required"] == list(params["properties"])
    assert "employee_id" not in json.dumps(TOOL_SCHEMAS)
    assert "manager_id" not in json.dumps(TOOL_SCHEMAS)  # the team comes from the token too


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
    owner, stored = repository.get_proposal("EMP-001", proposal.proposal_id)
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


# --- Team analytics (managers only) ---
# Teams come from data/employees.json: Sari (EMP-010) manages Alya, Bima, Citra, Dimas (4 people);
# Dewi (EMP-020) manages Eka, Fajar, Gita (3 people). December 2026: the 5th and 6th are a weekend.

SARI = AuthContext(employee_id="EMP-010", display_name="Sari Wijaya", role="manager")
DEWI = AuthContext(employee_id="EMP-020", display_name="Dewi Anggraini", role="manager")


def add_team_request(repository: MemoryRepository, owner: str, start: date, end: date, days: int, status: str,
                     created: datetime = datetime(2026, 9, 1, 3, tzinfo=timezone.utc), leave_type: str = "annual") -> None:
    repository.requests.append((owner, LeaveRequestView(
        request_id=f"LR-{owner}-{start:%m%d}", leave_type=leave_type, start_date=start, end_date=end,
        business_days=days, status=status, created_at=created,
    )))


@pytest.fixture
def team(repository: MemoryRepository) -> MemoryRepository:
    add = add_team_request
    add(repository, "EMP-011", date(2026, 12, 1), date(2026, 12, 3), 3, "approved")  # Citra
    add(repository, "EMP-012", date(2026, 12, 2), date(2026, 12, 4), 3, "pending_manager_review",  # Dimas
        created=datetime(2026, 9, 10, 3, tzinfo=timezone.utc))
    add(repository, "EMP-011", date(2026, 12, 21), date(2026, 12, 22), 2, "pending_manager_review",  # Citra
        created=datetime(2026, 9, 13, 20, tzinfo=timezone.utc))  # 14 September in WIB
    add(repository, "EMP-001", date(2026, 12, 4), date(2026, 12, 7), 2, "approved")  # Alya, Fri-Mon
    add(repository, "EMP-002", date(2026, 12, 4), date(2026, 12, 7), 2, "approved")  # Bima, Fri-Mon
    add(repository, "EMP-012", date(2026, 12, 15), date(2026, 12, 15), 1, "cancelled")  # never counted
    add(repository, "EMP-010", date(2026, 12, 28), date(2026, 12, 29), 2, "pending_manager_review")  # Sari's own
    add(repository, "EMP-021", date(2026, 12, 7), date(2026, 12, 9), 3, "approved")  # Eka, Dewi's team
    add(repository, "EMP-022", date(2026, 12, 8), date(2026, 12, 10), 3, "pending_manager_review",  # Fajar
        created=datetime(2026, 9, 15, 3, tzinfo=timezone.utc), leave_type="sick")
    return repository


def team_call(tools: ToolExecutor, auth: AuthContext, metric: str, start: str | None, end: str | None) -> dict:
    result, proposal = tools.execute(
        "get_team_leave_analytics", {"metric": metric, "start_date": start, "end_date": end}, auth
    )
    assert proposal is None  # analytics never prepares an action
    return result


def test_team_tool_is_for_managers_only(tools: ToolExecutor, team: MemoryRepository) -> None:
    for metric in ("team_absence", "coverage_risk"):
        result = team_call(tools, ALYA, metric, "2026-12-01", "2026-12-05")
        assert result["status"] == "blocked" and "manajer" in result["reason"]
    assert team_call(tools, ALYA, "pending_queue", None, None)["status"] == "blocked"


def test_team_tool_refuses_a_team_named_in_the_arguments(tools: ToolExecutor, team: MemoryRepository) -> None:
    result, _ = tools.execute(
        "get_team_leave_analytics",
        {"metric": "pending_queue", "start_date": None, "end_date": None, "manager_id": "EMP-020"},
        SARI,
    )
    assert result["status"] == "blocked" and "manager_id" in result["reason"]


def test_team_absence_lists_overlapping_leave_of_own_team(tools: ToolExecutor, team: MemoryRepository) -> None:
    result = team_call(tools, SARI, "team_absence", "2026-12-01", "2026-12-03")
    assert result["status"] == "ok"
    assert result["team_size"] == 4 and result["people_on_leave"] == 2
    assert [(r["name"], r["status"]) for r in result["requests"]] == [
        ("Citra Lestari", "approved"), ("Dimas Saputra", "pending_manager_review"),
    ]  # Alya and Bima start on the 4th; the cancelled and Sari's own request never show

    dewi = team_call(tools, DEWI, "team_absence", "2026-12-01", "2026-12-31")
    assert dewi["team_size"] == 3
    assert [r["name"] for r in dewi["requests"]] == ["Eka Putri", "Fajar Nugroho"]  # never Sari's team


def test_pending_queue_puts_the_longest_wait_first(tools: ToolExecutor, team: MemoryRepository) -> None:
    result = team_call(tools, SARI, "pending_queue", None, None)
    assert result["status"] == "ok" and result["pending_count"] == 2 and result["today"] == "2026-09-23"
    assert [(r["name"], r["submitted_on"], r["days_waiting"]) for r in result["requests"]] == [
        ("Dimas Saputra", "2026-09-10", 13),
        ("Citra Lestari", "2026-09-14", 9),  # created 13 Sep 20:00 UTC = 14 Sep in WIB
    ]

    with_period = team_call(tools, SARI, "pending_queue", "2026-12-01", "2026-12-31")
    assert with_period["status"] == "blocked"  # refused, not silently ignored


def test_coverage_risk_counts_business_days_at_or_above_30_percent(tools: ToolExecutor, team: MemoryRepository) -> None:
    result = team_call(tools, SARI, "coverage_risk", "2026-11-30", "2026-12-08")
    assert result["status"] == "ok" and result["team_size"] == 4 and result["threshold_percent"] == 30
    assert [(d["date"], d["people_on_leave"], d["percent"], d["names"]) for d in result["risky_days"]] == [
        ("2026-12-02", 2, 50, ["Citra Lestari", "Dimas Saputra"]),
        ("2026-12-03", 2, 50, ["Citra Lestari", "Dimas Saputra"]),
        ("2026-12-04", 3, 75, ["Alya Pratama", "Bima Santoso", "Dimas Saputra"]),
        ("2026-12-07", 2, 50, ["Alya Pratama", "Bima Santoso"]),
    ]  # 1 Dec is 1 of 4 = 25%; 5-6 Dec (Alya and Bima away) are a weekend

    dewi = team_call(tools, DEWI, "coverage_risk", "2026-12-07", "2026-12-11")
    assert [(d["date"], d["percent"]) for d in dewi["risky_days"]] == [
        ("2026-12-07", 33), ("2026-12-08", 67), ("2026-12-09", 67), ("2026-12-10", 33),
    ]  # 1 of 3 is already above 30%; 2 of 3 = 66.7 rounds to 67


@pytest.mark.parametrize(
    "metric,start,end,reason",
    [
        ("team_absence", None, None, "butuh start_date"),
        ("coverage_risk", "2026-12-01", None, "butuh start_date"),
        ("team_absence", "2026-12-10", "2026-12-01", "sebelum tanggal awal"),
        ("coverage_risk", "2026-12-01", "2027-01-01", "paling lama 31 hari"),  # 32 days
    ],
)
def test_team_period_rules(tools: ToolExecutor, team: MemoryRepository, metric, start, end, reason) -> None:
    result = team_call(tools, SARI, metric, start, end)
    assert result["status"] == "blocked" and reason in result["reason"]


def test_team_period_of_exactly_31_days_is_allowed(tools: ToolExecutor, team: MemoryRepository) -> None:
    assert team_call(tools, SARI, "coverage_risk", "2026-12-01", "2026-12-31")["status"] == "ok"


def test_team_results_show_names_only(tools: ToolExecutor, team: MemoryRepository) -> None:
    results = [
        team_call(tools, SARI, "team_absence", "2026-12-01", "2026-12-31"),
        team_call(tools, SARI, "pending_queue", None, None),
        team_call(tools, SARI, "coverage_risk", "2026-12-01", "2026-12-31"),
    ]
    text = json.dumps(results)
    assert all(r["status"] == "ok" for r in results)
    assert "EMP-" not in text and "LR-" not in text  # no employee or request IDs
    for hidden in ("reason", "balance", "available"):
        assert hidden not in text
