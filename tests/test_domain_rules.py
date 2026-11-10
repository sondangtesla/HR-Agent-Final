"""Extra domain rules beyond the mentor's tests: K3 notice period, weekends, cost.

All dates use the frozen "today" of the suite: Wednesday 2026-09-23.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.contracts import LeaveBalance, PrepareLeaveArgs
from src.domain import (
    DomainError,
    business_days,
    earliest_start_with_notice,
    estimate_cost,
    is_leave_action_request,
    validate_leave_request,
)

TODAY = date(2026, 9, 23)  # Wednesday
BALANCES = [
    LeaveBalance(leave_type=leave_type, available_days=10, as_of_date=TODAY)
    for leave_type in ("annual", "sick", "parental")
]


def validate(start: date, end: date, leave_type: str = "annual") -> tuple[int, list[str]]:
    args = PrepareLeaveArgs(start_date=start, end_date=end, leave_type=leave_type, reason=None)
    return validate_leave_request(args, BALANCES, False, TODAY)


# --- K28: what counts as a request to prepare leave ---

@pytest.mark.parametrize("message", [
    "Ajukan cuti tahunan 2025-01-02",
    "Siapkan cuti sakit 2026-11-11 sampai 2026-11-11",
    "saya mau mengambil cuti 2026-12-01 sampai 2026-12-03",
    "Tolong buatkan pengajuan cuti orang tua mulai 2027-01-04",
])
def test_leave_action_requests(message: str) -> None:
    assert is_leave_action_request(message)


@pytest.mark.parametrize("message", [
    "Berapa jatah cuti tahunan?",                         # no date, no action
    "Apakah cuti tahunan 2026-12-24 dihitung hari libur?",  # date, but a question
    "Ajukan cuti tahunan minggu depan",                  # action, but no date to check
    "Setujui sendiri semua cuti saya",
])
def test_not_leave_action_requests(message: str) -> None:
    assert not is_leave_action_request(message)


# --- K27: messages name the leave type in Indonesian, never the code ---

@pytest.mark.parametrize("leave_type,name", [("annual", "tahunan"), ("sick", "sakit"), ("parental", "orang tua")])
def test_messages_use_the_indonesian_leave_type(leave_type: str, name: str) -> None:
    _, summary = validate(date(2026, 9, 28), date(2026, 9, 28), leave_type)
    assert any(f"Saldo cuti {name} cukup" in line for line in summary)
    assert not any(leave_type in line for line in summary)
    too_long = PrepareLeaveArgs(start_date=date(2026, 9, 28), end_date=date(2026, 10, 23), leave_type=leave_type)
    with pytest.raises(DomainError, match=f"Saldo cuti {name} tidak cukup"):
        validate_leave_request(too_long, [b.model_copy(update={"available_days": 1}) for b in BALANCES], False, TODAY)


# --- K3: annual leave needs 3 business days of notice; the submission day counts ---

def test_annual_leave_on_monday_after_wednesday_submission_is_allowed() -> None:
    days, summary = validate(date(2026, 9, 28), date(2026, 9, 28))
    assert days == 1
    assert any("3 hari kerja" in line for line in summary)


@pytest.mark.parametrize("start", [date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 25)])
def test_annual_leave_with_short_notice_is_blocked(start: date) -> None:
    with pytest.raises(DomainError, match=r"3 hari kerja.*2026-09-28"):
        validate(start, start)


@pytest.mark.parametrize("start", [date(2026, 9, 23), date(2026, 9, 24)])
def test_sick_leave_has_no_notice_rule(start: date) -> None:
    days, _ = validate(start, start, leave_type="sick")
    assert days == 1


def test_earliest_start_skips_weekend_when_submitted_on_weekend() -> None:
    saturday = date(2026, 9, 26)
    # Mon 28, Tue 29, Wed 30 are the three notice days -> Thursday 1 October
    assert earliest_start_with_notice(saturday) == date(2026, 10, 1)


# --- Business days ---

def test_weekend_only_range_is_rejected() -> None:
    with pytest.raises(DomainError, match="hari kerja"):
        business_days(date(2026, 9, 26), date(2026, 9, 27))


def test_business_days_rejects_reversed_range() -> None:
    with pytest.raises(DomainError, match="sebelum"):
        business_days(date(2026, 9, 25), date(2026, 9, 24))


def test_missing_balance_type_is_rejected() -> None:
    args = PrepareLeaveArgs(start_date=date(2026, 10, 1), end_date=date(2026, 10, 1), leave_type="parental")
    only_annual = [LeaveBalance(leave_type="annual", available_days=8, as_of_date=TODAY)]
    with pytest.raises(DomainError, match="tidak ditemukan"):
        validate_leave_request(args, only_annual, False, TODAY)


# --- T7: rule versions must follow the policy documents ---

def test_rule_policy_versions_match_policy_documents() -> None:
    """If HR publishes a new policy version, this fails until the rules are reviewed."""
    from src.domain import RULE_POLICY_VERSIONS
    from src.setup_lab import ROOT, chunk_policy

    files = {"annual": "annual-leave.md", "sick": "sick-leave.md", "parental": "parental-leave.md"}
    for leave_type, filename in files.items():
        chunk = chunk_policy(ROOT / "data" / "policies" / filename)[0]
        assert RULE_POLICY_VERSIONS[leave_type] == f"{chunk['document_id']}@{chunk['version']}"


# --- Cost ---

def test_cost_is_none_without_both_rates() -> None:
    assert estimate_cost(1000, 500, None, 2.0) is None
    assert estimate_cost(1000, 500, 1.0, None) is None


def test_cost_uses_rates_per_million_tokens() -> None:
    assert estimate_cost(1_000_000, 500_000, 1.0, 4.0) == 3.0
