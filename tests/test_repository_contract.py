"""One contract, two repositories: MemoryRepository and PostgresRepository must agree.

The PostgreSQL run needs a seeded database (python -m src.setup_lab). It is skipped when the
database is unreachable or unseeded, and it deletes every row it creates (IDs start with TEST-).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from src.config import get_settings
from src.contracts import ActionProposal, LeaveRequestView, PrepareLeaveArgs
from src.domain import DomainError, effective_balances, validate_leave_request
from src.repository import MemoryRepository, PostgresRepository

TODAY = date(2026, 9, 23)  # Wednesday, same frozen day as the rest of the suite


def _cleanup(repo: PostgresRepository) -> None:
    with repo.pool.connection() as conn:
        conn.execute("DELETE FROM leave_requests WHERE request_id LIKE 'TEST-%%'")
        conn.execute("DELETE FROM action_proposals WHERE proposal_id LIKE 'AP-TEST-%%'")
        conn.execute("DELETE FROM hr_tickets WHERE summary LIKE '%%TEST-MARKER%%'")


@pytest.fixture(scope="module")
def postgres_repo():
    settings = get_settings()
    repo = PostgresRepository(settings.database_url, settings.embedding_dimensions)
    if not repo.health() or repo.authenticate("token-alya") is None:
        repo.close()
        pytest.skip("PostgreSQL is not reachable or not seeded")
    yield repo
    repo.close()


@pytest.fixture(params=["memory", "postgres"])
def repo(request):
    if request.param == "memory":
        yield MemoryRepository()
        return
    pg = request.getfixturevalue("postgres_repo")
    _cleanup(pg)
    yield pg
    _cleanup(pg)


def add_request(repo, employee_id: str, request_id: str, leave_type: str,
                start: date, end: date, days: int, status: str, created: datetime | None = None) -> None:
    """Test setup only: put a request in place as if the HR system had written it."""
    created = created or datetime(2026, 9, 1, tzinfo=timezone.utc)
    if isinstance(repo, MemoryRepository):
        repo.requests.append((employee_id, LeaveRequestView(
            request_id=request_id, leave_type=leave_type, start_date=start, end_date=end,
            business_days=days, status=status, created_at=created,
        )))
        return
    with repo.pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO leave_requests (request_id, employee_id, leave_type, start_date, end_date,
                                        business_days, status, status_set_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'hr_system', %s)
            """,
            (request_id, employee_id, leave_type, start, end, days, status, created),
        )


def make_proposal(proposal_id: str, leave_type: str = "annual") -> ActionProposal:
    return ActionProposal(
        proposal_id=proposal_id, leave_type=leave_type,
        start_date=date(2026, 10, 5), end_date=date(2026, 10, 6), business_days=2,
        reason="Liburan keluarga", validation_summary=["Rentang valid."],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )


# --- Identity and balances ---

def test_demo_tokens_authenticate(repo) -> None:
    assert repo.authenticate("token-alya").employee_id == "EMP-001"
    assert repo.authenticate("token-admin").role == "monitoring_admin"
    assert repo.authenticate("token-tidak-ada") is None
    assert repo.authenticate("") is None


def test_balances_belong_to_one_employee(repo) -> None:
    alya = {b.leave_type: b.available_days for b in repo.get_balances("EMP-001")}
    bima = {b.leave_type: b.available_days for b in repo.get_balances("EMP-002")}
    assert alya["annual"] == 8 and bima["annual"] == 3
    assert repo.get_balances("ADM-001") == []


# --- K8: effective balance ---

def test_pending_days_count_only_pending_requests_of_that_employee(repo) -> None:
    add_request(repo, "EMP-001", "TEST-P1", "annual", date(2026, 10, 5), date(2026, 10, 9), 5, "pending_manager_review")
    add_request(repo, "EMP-001", "TEST-P2", "sick", date(2026, 10, 12), date(2026, 10, 13), 2, "pending_manager_review")
    add_request(repo, "EMP-001", "TEST-A1", "annual", date(2026, 8, 3), date(2026, 8, 4), 2, "approved")
    add_request(repo, "EMP-001", "TEST-C1", "annual", date(2026, 8, 10), date(2026, 8, 10), 1, "cancelled")
    add_request(repo, "EMP-002", "TEST-P3", "annual", date(2026, 10, 5), date(2026, 10, 5), 1, "pending_manager_review")
    repo.save_proposal("EMP-001", make_proposal("AP-TEST-UNCONFIRMED"))  # not confirmed: not counted

    assert repo.get_pending_days("EMP-001") == {"annual": 5, "sick": 2}
    assert repo.get_pending_days("EMP-002") == {"annual": 1}


def test_effective_balance_blocks_second_request(repo) -> None:
    """Annual balance 8 with 5 days pending: a new 5-day request fails, a 3-day one passes."""
    add_request(repo, "EMP-001", "TEST-P1", "annual", date(2026, 10, 5), date(2026, 10, 9), 5, "pending_manager_review")
    balances = effective_balances(repo.get_balances("EMP-001"), repo.get_pending_days("EMP-001"))

    five_days = PrepareLeaveArgs(start_date=date(2026, 10, 19), end_date=date(2026, 10, 23), leave_type="annual")
    with pytest.raises(DomainError, match="tidak cukup.*tersedia 3 hari"):
        validate_leave_request(five_days, balances, False, TODAY)

    three_days = PrepareLeaveArgs(start_date=date(2026, 10, 19), end_date=date(2026, 10, 21), leave_type="annual")
    assert validate_leave_request(three_days, balances, False, TODAY)[0] == 3

    # The stored balance itself never changes.
    assert {b.leave_type: b.available_days for b in repo.get_balances("EMP-001")}["annual"] == 8


# --- Overlap ---

@pytest.mark.parametrize(
    "status,start,end,expected",
    [
        ("pending_manager_review", date(2026, 10, 9), date(2026, 10, 12), True),   # shares 9 Oct
        ("approved", date(2026, 10, 1), date(2026, 10, 5), True),                  # shares 5 Oct
        ("cancelled", date(2026, 10, 5), date(2026, 10, 9), False),                # cancelled frees dates
        ("pending_manager_review", date(2026, 10, 12), date(2026, 10, 13), False), # day after
    ],
)
def test_overlap_counts_active_requests_only(repo, status, start, end, expected) -> None:
    add_request(repo, "EMP-001", "TEST-O1", "annual", date(2026, 10, 5), date(2026, 10, 9), 5, status)
    assert repo.has_overlap("EMP-001", start, end) is expected
    assert repo.has_overlap("EMP-002", start, end) is False  # someone else's dates never block


# --- Proposals, requests, tickets ---

def test_proposal_round_trip_keeps_owner(repo) -> None:
    proposal = make_proposal("AP-TEST-ROUNDTRIP")
    repo.save_proposal("EMP-001", proposal)
    owner, stored = repo.get_proposal("AP-TEST-ROUNDTRIP")
    assert owner == "EMP-001"
    assert stored.model_dump() == proposal.model_dump()
    assert repo.get_proposal("AP-TEST-MISSING") is None


def test_requests_are_own_and_newest_first(repo) -> None:
    old = datetime(2026, 9, 1, tzinfo=timezone.utc)
    new = datetime(2026, 9, 20, tzinfo=timezone.utc)
    add_request(repo, "EMP-001", "TEST-OLD", "annual", date(2026, 10, 5), date(2026, 10, 5), 1, "approved", old)
    add_request(repo, "EMP-001", "TEST-NEW", "sick", date(2026, 10, 7), date(2026, 10, 7), 1, "pending_manager_review", new)
    add_request(repo, "EMP-002", "TEST-BIMA", "annual", date(2026, 10, 5), date(2026, 10, 5), 1, "approved", new)
    mine = [r.request_id for r in repo.list_leave_requests("EMP-001") if r.request_id.startswith("TEST-")]
    assert mine == ["TEST-NEW", "TEST-OLD"]


def test_ticket_summary_is_redacted_when_stored(repo) -> None:
    ticket_id = repo.create_ticket("EMP-001", "privacy", "TEST-MARKER hubungi alya@example.com, diagnosis: diabetes")
    assert ticket_id.startswith("HRT-")
    if isinstance(repo, MemoryRepository):
        summary = repo.tickets[-1]["summary"]
    else:
        with repo.pool.connection() as conn:
            summary = conn.execute("SELECT summary FROM hr_tickets WHERE ticket_id = %s", (ticket_id,)).fetchone()["summary"]
    assert "alya@example.com" not in summary and "diabetes" not in summary
