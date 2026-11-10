"""Guards that live in PostgreSQL itself, so they hold even when the Python code has a bug.

- K9: CHECK and UNIQUE constraints on leave_requests (run as the table owner).
- K9 option C: what the API login (hr_api) may and may not do.
- K26: hr_api may lower a balance but never raise it; HR cancellation refunds the days.

Every case runs in a transaction that is rolled back. Skipped when PostgreSQL is not seeded.
"""
from __future__ import annotations

import psycopg
import pytest

from src.config import get_settings

PENDING = "pending_manager_review"


def _connect(url: str) -> psycopg.Connection:
    try:
        conn = psycopg.connect(url, connect_timeout=3)
    except psycopg.Error:
        pytest.skip("PostgreSQL is not reachable or the hr_api role is not seeded")
    if not conn.execute("SELECT to_regclass('leave_requests')").fetchone()[0]:
        conn.close()
        pytest.skip("schema is not seeded")
    return conn


@pytest.fixture
def owner():
    conn = _connect(get_settings().database_url)
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def api():
    conn = _connect(get_settings().api_database_url)
    yield conn
    conn.rollback()
    conn.close()


def setup_proposal(owner: psycopg.Connection) -> None:
    owner.execute(
        """INSERT INTO action_proposals (proposal_id, employee_id, leave_type, start_date, end_date,
           business_days, policy_version, expires_at)
           VALUES ('AP-GUARD', 'EMP-001', 'annual', '2026-12-01', '2026-12-02', 2, 'HR-LEAVE-001@2.1', now())"""
    )


def insert_request(conn, request_id="LR-GUARD-1", status=PENDING, by="assistant",
                   proposal_id="AP-GUARD", key="key-guard-1", policy="HR-LEAVE-001@2.1") -> None:
    conn.execute(
        """INSERT INTO leave_requests (request_id, employee_id, leave_type, start_date, end_date,
           business_days, status, status_set_by, proposal_id, idempotency_key, policy_version)
           VALUES (%s, 'EMP-001', 'annual', '2026-12-01', '2026-12-02', 2, %s, %s, %s, %s, %s)""",
        (request_id, status, by, proposal_id, key, policy),
    )


def violated_constraint(conn, action) -> str | None:
    """Run action inside a savepoint; return the violated constraint name, or None if accepted."""
    try:
        with conn.transaction():
            action()
    except psycopg.errors.IntegrityError as exc:
        return exc.diag.constraint_name
    return None


# --- K9 constraints (as the table owner, so only constraints can stop the write) ---

def test_assistant_can_write_pending(owner) -> None:
    setup_proposal(owner)
    assert violated_constraint(owner, lambda: insert_request(owner)) is None


def test_assistant_cannot_write_approved(owner) -> None:
    setup_proposal(owner)
    assert violated_constraint(owner, lambda: insert_request(owner, status="approved")) == "assistant_writes_only_pending"


def test_seed_may_write_history_and_hr_may_approve(owner) -> None:
    setup_proposal(owner)
    assert violated_constraint(owner, lambda: insert_request(
        owner, "LR-GUARD-H", status="approved", by="seed", proposal_id=None, key=None, policy=None)) is None
    insert_request(owner)
    approve = "UPDATE leave_requests SET status = 'approved', status_set_by = 'hr_system' WHERE request_id = 'LR-GUARD-1'"
    assert violated_constraint(owner, lambda: owner.execute(approve)) is None


def test_assistant_request_needs_policy_version(owner) -> None:
    setup_proposal(owner)
    assert violated_constraint(owner, lambda: insert_request(owner, policy=None)) == \
        "assistant_request_has_proposal_key_and_policy"


def test_one_request_per_proposal_and_per_key(owner) -> None:
    setup_proposal(owner)
    insert_request(owner)
    assert violated_constraint(owner, lambda: insert_request(owner, "LR-GUARD-2", key="key-guard-2")) == \
        "leave_requests_proposal_id_key"
    assert violated_constraint(owner, lambda: insert_request(
        owner, "LR-GUARD-3", by="seed", proposal_id=None, policy=None)) == \
        "leave_requests_employee_id_idempotency_key_key"


def test_unknown_status_and_raw_token_are_rejected(owner) -> None:
    setup_proposal(owner)
    assert violated_constraint(owner, lambda: insert_request(owner, status="rejected", by="hr_system")) == \
        "leave_requests_status_check"
    raw_token = "INSERT INTO employees VALUES ('EMP-999', 'X', 'employee', 'token-alya')"
    assert violated_constraint(owner, lambda: owner.execute(raw_token)) == "employees_token_hash_check"


# --- K9 option C: the API login is not a superuser and cannot approve anything ---

def denied(conn, statement: str) -> bool:
    try:
        with conn.transaction():
            conn.execute(statement)
    except psycopg.errors.InsufficientPrivilege:
        return True
    return False


def test_api_login_is_hr_api_without_special_powers(api) -> None:
    user, superuser, bypass = api.execute(
        "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    assert (user, superuser, bypass) == ("hr_api", False, False)
    api.execute("RESET ROLE")  # the SET ROLE escape hatch does not exist for this login
    assert api.execute("SELECT current_user").fetchone()[0] == "hr_api"
    assert denied(api, "SET ROLE hr_app")


def test_api_cannot_approve_even_when_claiming_to_be_hr(api) -> None:
    # status_set_by is just a column; the row-level security policy ignores what it claims.
    statement = """INSERT INTO leave_requests (request_id, employee_id, leave_type, start_date, end_date,
                   business_days, status, status_set_by)
                   VALUES ('LR-GUARD-X', 'EMP-001', 'annual', '2026-12-01', '2026-12-01', 1,
                           'approved', 'hr_system')"""
    assert denied(api, statement)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE leave_requests SET status = 'approved'",
        "DELETE FROM leave_requests",
        "UPDATE leave_balances SET available_days = 99",
        "INSERT INTO employees VALUES ('EMP-999', 'X', 'employee', repeat('a', 64))",
        "UPDATE action_proposals SET expires_at = now() + interval '1 year'",
        "DELETE FROM traces",
        "DROP TABLE employees",
    ],
)
def test_api_cannot_change_what_it_does_not_own(api, statement: str) -> None:
    assert denied(api, statement)


def test_api_can_read_what_it_needs(api) -> None:
    for table in ("employees", "leave_balances", "policy_chunks", "leave_requests", "action_proposals", "traces"):
        api.execute(f"SELECT 1 FROM {table} LIMIT 1")  # constant table names


# --- K26: the API may lower a balance, never raise it, and touches nothing else ---

def annual(conn) -> int:
    return conn.execute(
        "SELECT available_days FROM leave_balances WHERE employee_id = 'EMP-001' AND leave_type = 'annual'"
    ).fetchone()[0]


def test_api_can_lower_a_balance_and_the_change_is_stamped(api) -> None:
    before = annual(api)
    stamped = api.execute(  # rolled back by the fixture
        """UPDATE leave_balances SET available_days = available_days - 1
           WHERE employee_id = 'EMP-001' AND leave_type = 'annual' RETURNING updated_at"""
    ).fetchone()[0]
    assert annual(api) == before - 1
    assert stamped is not None  # set by the trigger, not by the caller


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE leave_balances SET available_days = available_days + 1 WHERE employee_id = 'EMP-001'",
        "UPDATE leave_balances SET employee_id = 'EMP-002' WHERE employee_id = 'EMP-001'",
        "UPDATE leave_balances SET leave_type = 'sick' WHERE employee_id = 'EMP-001' AND leave_type = 'annual'",
        "UPDATE leave_balances SET as_of_date = '2030-01-01'",
        "UPDATE leave_balances SET updated_at = now()",
        "INSERT INTO leave_balances VALUES ('EMP-001', 'annual', 99, now()::date)",
        "DELETE FROM leave_balances",
    ],
)
def test_api_cannot_raise_move_or_create_a_balance(api, statement: str) -> None:
    before = annual(api)
    assert denied(api, statement)
    assert annual(api) == before


def test_balance_can_never_go_negative(api) -> None:
    lower_everything = "UPDATE leave_balances SET available_days = available_days - 1000 WHERE employee_id = 'EMP-001'"
    assert violated_constraint(api, lambda: api.execute(lower_everything)) == "leave_balances_available_days_check"


def test_hr_cancelling_an_assistant_request_refunds_the_days(owner) -> None:
    setup_proposal(owner)
    insert_request(owner)  # 2 business days, made through the assistant
    before = annual(owner)
    owner.execute("UPDATE leave_requests SET status = 'cancelled', status_set_by = 'hr_system' WHERE request_id = 'LR-GUARD-1'")
    assert annual(owner) == before + 2


def test_hr_approving_keeps_the_balance(owner) -> None:
    setup_proposal(owner)
    insert_request(owner)
    before = annual(owner)
    owner.execute("UPDATE leave_requests SET status = 'approved', status_set_by = 'hr_system' WHERE request_id = 'LR-GUARD-1'")
    assert annual(owner) == before  # already deducted at confirmation


def test_cancelling_seeded_history_is_not_refunded(owner) -> None:
    insert_request(owner, "LR-GUARD-H", status="approved", by="seed", proposal_id=None, key=None, policy=None)
    before = annual(owner)
    owner.execute("UPDATE leave_requests SET status = 'cancelled', status_set_by = 'hr_system' WHERE request_id = 'LR-GUARD-H'")
    assert annual(owner) == before  # this system never deducted it
