"""One contract, two repositories: MemoryRepository and PostgresRepository must agree.

The PostgreSQL run needs a seeded database (python -m src.setup_lab). It is skipped when the
database is unreachable or unseeded, and it deletes every row it creates.

Tests that change data use two test-only employees, A and B, created and removed by the
fixture. They never touch the demo employees, whose data changes when someone uses the app
(e.g. a confirmed leave request for Alya would shift every balance assertion).
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.rows import dict_row

from src.config import get_settings
from src.contracts import ActionProposal, LeaveBalance, LeaveRequestView, PrepareLeaveArgs
from src.domain import DomainError, validate_leave_request
from src.repository import ConflictError, MemoryRepository, PostgresRepository

TODAY = date(2026, 9, 23)  # Wednesday, same frozen day as the rest of the suite
A, B = "EMP-901", "EMP-902"  # test-only employees: annual balance 8 and 3, like Alya and Bima
TEST_BALANCES = {A: {"annual": 8, "sick": 10, "parental": 60}, B: {"annual": 3, "sick": 10, "parental": 60}}


def admin_execute(sql: str, params: tuple = ()) -> list[dict]:
    with psycopg.connect(get_settings().database_url, autocommit=True, row_factory=dict_row) as conn:
        cursor = conn.execute(sql, params)
        return cursor.fetchall() if cursor.description else []


def _cleanup() -> None:
    ids = list(TEST_BALANCES)
    for table in ("leave_requests", "action_proposals", "hr_tickets", "traces", "leave_balances", "employees"):
        admin_execute(f"DELETE FROM {table} WHERE employee_id = ANY(%s)", (ids,))  # constant table names


def _create_test_employees() -> None:
    for number, (employee_id, balances) in enumerate(TEST_BALANCES.items()):
        admin_execute(
            "INSERT INTO employees VALUES (%s, %s, 'employee', %s)",
            (employee_id, f"Test Employee {employee_id}", f"{number:064d}"),
        )
        for leave_type, days in balances.items():
            admin_execute(
                "INSERT INTO leave_balances VALUES (%s, %s, %s, %s)", (employee_id, leave_type, days, TODAY)
            )


@pytest.fixture(scope="module")
def postgres_repo():
    settings = get_settings()
    repo = PostgresRepository(settings.api_database_url, settings.embedding_dimensions)
    if not repo.health() or repo.authenticate("token-alya") is None:
        repo.close()
        pytest.skip("PostgreSQL is not reachable or not seeded")
    yield repo
    repo.close()


@pytest.fixture(params=["memory", "postgres"])
def repo(request):
    if request.param == "memory":
        memory = MemoryRepository()
        for employee_id, balances in TEST_BALANCES.items():
            memory.balances[employee_id] = [
                LeaveBalance(leave_type=t, available_days=d, as_of_date=TODAY) for t, d in balances.items()
            ]
        yield memory
        return
    pg = request.getfixturevalue("postgres_repo")
    _cleanup()
    _create_test_employees()
    yield pg
    _cleanup()


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
    admin_execute(
        """
        INSERT INTO leave_requests (request_id, employee_id, leave_type, start_date, end_date,
                                    business_days, status, status_set_by, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'hr_system', %s)
        """,
        (request_id, employee_id, leave_type, start, end, days, status, created),
    )


def make_proposal(proposal_id: str, leave_type: str = "annual", start: date = date(2026, 10, 5),
                  end: date = date(2026, 10, 6), days: int = 2) -> ActionProposal:
    return ActionProposal(
        proposal_id=proposal_id, leave_type=leave_type,
        start_date=start, end_date=end, business_days=days,
        reason="Liburan keluarga", validation_summary=["Rentang valid."],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )


def expire(repo, proposal_id: str) -> None:
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    if isinstance(repo, MemoryRepository):
        owner, proposal = repo.proposals[proposal_id]
        repo.proposals[proposal_id] = (owner, proposal.model_copy(update={"expires_at": past}))
    else:
        admin_execute("UPDATE action_proposals SET expires_at = %s WHERE proposal_id = %s", (past, proposal_id))


# --- Identity and balances ---

def test_demo_tokens_authenticate(repo) -> None:
    assert repo.authenticate("token-alya").employee_id == "EMP-001"
    assert repo.authenticate("token-admin").role == "monitoring_admin"
    assert repo.authenticate("token-tidak-ada") is None
    assert repo.authenticate("") is None


def test_balances_belong_to_one_employee(repo) -> None:
    alya = {b.leave_type: b.available_days for b in repo.get_balances(A)}
    bima = {b.leave_type: b.available_days for b in repo.get_balances(B)}
    assert alya["annual"] == 8 and bima["annual"] == 3
    assert repo.get_balances("ADM-001") == []


# --- Pending days (information only) and K26 deduction ---

def test_pending_days_count_only_pending_requests_of_that_employee(repo) -> None:
    add_request(repo, A, "TEST-P1", "annual", date(2026, 10, 5), date(2026, 10, 9), 5, "pending_manager_review")
    add_request(repo, A, "TEST-P2", "sick", date(2026, 10, 12), date(2026, 10, 13), 2, "pending_manager_review")
    add_request(repo, A, "TEST-A1", "annual", date(2026, 8, 3), date(2026, 8, 4), 2, "approved")
    add_request(repo, A, "TEST-C1", "annual", date(2026, 8, 10), date(2026, 8, 10), 1, "cancelled")
    add_request(repo, B, "TEST-P3", "annual", date(2026, 10, 5), date(2026, 10, 5), 1, "pending_manager_review")
    repo.save_proposal(A, make_proposal("AP-TEST-UNCONFIRMED"))  # not confirmed: not counted

    assert repo.get_pending_days(A) == {"annual": 5, "sick": 2}
    assert repo.get_pending_days(B) == {"annual": 1}


def annual_balance(repo, employee_id: str = A) -> int:
    return {b.leave_type: b.available_days for b in repo.get_balances(employee_id)}["annual"]


def test_confirmed_days_are_deducted_so_the_next_validation_sees_them(repo) -> None:
    """K26: balance 8, a 5-day request confirmed -> stored balance 3; a new 5-day request fails."""
    repo.save_proposal(A, make_proposal("AP-TEST-P1", start=date(2026, 10, 5), end=date(2026, 10, 9), days=5))
    repo.confirm_proposal(A, "AP-TEST-P1", "key-test-0100")
    assert annual_balance(repo) == 3
    assert annual_balance(repo, B) == 3  # Bima's own balance, untouched (it was 3 already)

    five_days = PrepareLeaveArgs(start_date=date(2026, 10, 19), end_date=date(2026, 10, 23), leave_type="annual")
    with pytest.raises(DomainError, match="tidak cukup.*tersedia 3 hari"):
        validate_leave_request(five_days, repo.get_balances(A), False, TODAY)

    three_days = PrepareLeaveArgs(start_date=date(2026, 10, 19), end_date=date(2026, 10, 21), leave_type="annual")
    assert validate_leave_request(three_days, repo.get_balances(A), False, TODAY)[0] == 3


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
    add_request(repo, A, "TEST-O1", "annual", date(2026, 10, 5), date(2026, 10, 9), 5, status)
    assert repo.has_overlap(A, start, end) is expected
    assert repo.has_overlap(B, start, end) is False  # someone else's dates never block


# --- Proposals, requests, tickets ---

def test_proposal_round_trip_keeps_owner(repo) -> None:
    proposal = make_proposal("AP-TEST-ROUNDTRIP")
    repo.save_proposal(A, proposal)
    owner, stored = repo.get_proposal("AP-TEST-ROUNDTRIP")
    assert owner == A
    assert stored.model_dump() == proposal.model_dump()
    assert repo.get_proposal("AP-TEST-MISSING") is None


def test_requests_are_own_and_newest_first(repo) -> None:
    old = datetime(2026, 9, 1, tzinfo=timezone.utc)
    new = datetime(2026, 9, 20, tzinfo=timezone.utc)
    add_request(repo, A, "TEST-OLD", "annual", date(2026, 10, 5), date(2026, 10, 5), 1, "approved", old)
    add_request(repo, A, "TEST-NEW", "sick", date(2026, 10, 7), date(2026, 10, 7), 1, "pending_manager_review", new)
    add_request(repo, B, "TEST-BIMA", "annual", date(2026, 10, 5), date(2026, 10, 5), 1, "approved", new)
    mine = [r.request_id for r in repo.list_leave_requests(A) if r.request_id.startswith("TEST-")]
    assert mine == ["TEST-NEW", "TEST-OLD"]


def test_ticket_summary_is_redacted_when_stored(repo) -> None:
    ticket_id = repo.create_ticket(A, "privacy", "TEST-MARKER hubungi alya@example.com, diagnosis: diabetes")
    assert ticket_id.startswith("HRT-")
    if isinstance(repo, MemoryRepository):
        summary = repo.tickets[-1]["summary"]
    else:
        summary = admin_execute("SELECT summary FROM hr_tickets WHERE ticket_id = %s", (ticket_id,))[0]["summary"]
    assert "alya@example.com" not in summary and "diabetes" not in summary


# --- Step 8: confirmation boundary ---

def test_confirm_creates_one_pending_request_and_replays(repo) -> None:
    repo.save_proposal(A, make_proposal("AP-TEST-C1"))
    first = repo.confirm_proposal(A, "AP-TEST-C1", "key-test-0001")
    again = repo.confirm_proposal(A, "AP-TEST-C1", "key-test-0001")
    assert first.status == "pending_manager_review" and first.idempotent_replay is False
    assert again.request_id == first.request_id and again.idempotent_replay is True
    assert again.audit_reference == first.audit_reference
    mine = [r for r in repo.list_leave_requests(A) if r.request_id == first.request_id]
    assert len(mine) == 1 and mine[0].status == "pending_manager_review"
    assert annual_balance(repo) == 8 - 2  # K26: deducted once; the replay does not deduct again


def test_confirm_rejects_other_owner_other_key_and_reused_key(repo) -> None:
    repo.save_proposal(A, make_proposal("AP-TEST-C2"))
    repo.save_proposal(A, make_proposal("AP-TEST-C3", start=date(2026, 10, 12), end=date(2026, 10, 12), days=1))
    with pytest.raises(KeyError):
        repo.confirm_proposal(B, "AP-TEST-C2", "key-test-0002")  # Bima cannot confirm Alya's
    with pytest.raises(KeyError):
        repo.confirm_proposal(A, "AP-TEST-NOPE", "key-test-0002")
    repo.confirm_proposal(A, "AP-TEST-C2", "key-test-0002")
    with pytest.raises(ConflictError, match="key lain"):
        repo.confirm_proposal(A, "AP-TEST-C2", "key-test-0003")
    with pytest.raises(ConflictError, match="proposal lain"):
        repo.confirm_proposal(A, "AP-TEST-C3", "key-test-0002")
    assert annual_balance(repo) == 8 - 2  # only the one successful confirmation deducted
    assert annual_balance(repo, B) == 3


def test_expired_proposal_creates_nothing_but_a_retry_after_success_still_replays(repo) -> None:
    repo.save_proposal(A, make_proposal("AP-TEST-E1"))
    expire(repo, "AP-TEST-E1")
    with pytest.raises(ConflictError, match="expired"):
        repo.confirm_proposal(A, "AP-TEST-E1", "key-test-0004")
    assert repo.get_pending_days(A) == {}
    assert annual_balance(repo) == 8  # nothing deducted

    repo.save_proposal(A, make_proposal("AP-TEST-E2"))
    done = repo.confirm_proposal(A, "AP-TEST-E2", "key-test-0005")
    expire(repo, "AP-TEST-E2")  # the network dropped the answer; the user retries later
    assert repo.confirm_proposal(A, "AP-TEST-E2", "key-test-0005").request_id == done.request_id


def test_balance_is_checked_again_at_confirmation(repo) -> None:
    """Two 5-day proposals made while the balance was 8: the deduction allows only one (K26)."""
    repo.save_proposal(A, make_proposal("AP-TEST-K1", start=date(2026, 10, 5), end=date(2026, 10, 9), days=5))
    repo.save_proposal(A, make_proposal("AP-TEST-K2", start=date(2026, 10, 19), end=date(2026, 10, 23), days=5))
    repo.confirm_proposal(A, "AP-TEST-K1", "key-test-0006")
    with pytest.raises(ConflictError, match="tidak cukup.*tersedia 3 hari"):
        repo.confirm_proposal(A, "AP-TEST-K2", "key-test-0007")
    assert repo.get_pending_days(A) == {"annual": 5}
    assert annual_balance(repo) == 3  # the failed confirmation rolled back completely


def test_overlap_is_checked_again_at_confirmation(repo) -> None:
    repo.save_proposal(A, make_proposal("AP-TEST-O1"))
    repo.save_proposal(A, make_proposal("AP-TEST-O2"))  # same dates, made before O1 was confirmed
    repo.confirm_proposal(A, "AP-TEST-O1", "key-test-0008")
    with pytest.raises(ConflictError, match="bertumpang tindih"):
        repo.confirm_proposal(A, "AP-TEST-O2", "key-test-0009")


def _race(calls) -> list:
    """Start every call at the same moment; return each result or exception."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def run(index, call):
        barrier.wait()
        try:
            results[index] = call()
        except Exception as exc:  # noqa: BLE001 - the exception IS the result here
            results[index] = exc

    threads = [threading.Thread(target=run, args=(i, c)) for i, c in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_parallel_confirms_of_two_proposals_cannot_overspend(repo) -> None:
    repo.save_proposal(A, make_proposal("AP-TEST-R1", start=date(2026, 10, 5), end=date(2026, 10, 9), days=5))
    repo.save_proposal(A, make_proposal("AP-TEST-R2", start=date(2026, 10, 19), end=date(2026, 10, 23), days=5))
    results = _race([
        lambda: repo.confirm_proposal(A, "AP-TEST-R1", "key-test-0010"),
        lambda: repo.confirm_proposal(A, "AP-TEST-R2", "key-test-0011"),
    ])
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert sum(isinstance(r, ConflictError) for r in results) == 1
    assert repo.get_pending_days(A) == {"annual": 5}
    assert annual_balance(repo) == 3  # never negative, never deducted twice


def test_parallel_double_click_creates_one_request(repo) -> None:
    repo.save_proposal(A, make_proposal("AP-TEST-D1"))
    results = _race([lambda: repo.confirm_proposal(A, "AP-TEST-D1", "key-test-0012")] * 3)
    assert len({r.request_id for r in results}) == 1
    assert sorted(r.idempotent_replay for r in results) == [False, True, True]
    assert annual_balance(repo) == 8 - 2  # one request, one deduction
