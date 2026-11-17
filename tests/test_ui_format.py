"""The Streamlit client shows a leave proposal as readable text, not raw JSON."""
from __future__ import annotations

from datetime import date

import pytest

from ui_format import (
    alert_rows, confirmation_message, error_message, example_questions, leave_request_rows, long_date,
    outcome_label, proposal_markdown, status_label, technical_details, wib_time,
)

PROPOSAL = {
    "proposal_id": "AP-3f9c0a",
    "action_type": "leave_request",
    "leave_type": "annual",
    "start_date": "2026-11-23",
    "end_date": "2026-11-24",
    "business_days": 2,
    "reason": "Liburan keluarga",
    "validation_summary": [
        "Rentang 2026-11-23 s.d. 2026-11-24 berisi 2 hari kerja.",
        "Saldo cuti tahunan cukup: tersedia 8 hari, sisa 6 hari setelah pengajuan ini.",
    ],
    "expires_at": "2026-11-10T09:36:12.123456Z",
    "requires_confirmation": True,
}


def test_dates_are_written_out_in_indonesian() -> None:
    assert long_date("2026-11-23") == "Senin, 23 November 2026"
    assert long_date(date(2026, 12, 6)) == "Minggu, 6 Desember 2026"


@pytest.mark.parametrize("stamp", ["2026-11-10T09:36:12Z", "2026-11-10T09:36:12+00:00", "2026-11-10T16:36:12+07:00"])
def test_expiry_is_shown_in_wib(stamp: str) -> None:
    assert wib_time(stamp) == "16.36 WIB"


def test_proposal_is_readable_and_hides_technical_fields() -> None:
    text = proposal_markdown(PROPOSAL)
    for shown in ("Cuti tahunan", "Senin, 23 November 2026 – Selasa, 24 November 2026",
                  "2 hari kerja", "Liburan keluarga", "16.36 WIB", "✅ Saldo cuti tahunan cukup"):
        assert shown in text
    for hidden in ("AP-3f9c0a", "leave_request", "requires_confirmation", "expires_at", "{", "09.36"):
        assert hidden not in text


def test_one_day_leave_without_reason() -> None:
    text = proposal_markdown({**PROPOSAL, "leave_type": "sick", "end_date": "2026-11-23", "reason": None})
    assert "| Tanggal | Senin, 23 November 2026 |" in text
    assert "Cuti sakit" in text and "Alasan" not in text


def test_user_text_cannot_break_the_table() -> None:
    text = proposal_markdown({**PROPOSAL, "reason": "a | b\nc"})
    assert "| Alasan | a \\| b c |" in text


def test_status_words_are_translated() -> None:
    assert status_label("pending_manager_review") == "menunggu tinjauan manajer"
    assert status_label("something_new") == "something_new"  # unknown values are shown, never hidden
    assert confirmation_message({"request_id": "LR-1", "status": "pending_manager_review"}) == \
        "Permintaan LR-1 sudah dibuat dan menunggu tinjauan manajer (status: `pending_manager_review`)."


# --- Chat details, requests table, errors, alerts, example questions ---

def test_technical_details_keep_outcome_and_trace_for_the_grader() -> None:
    """docker-delivery.md: the answer must show its trace. It is folded away, not removed."""
    result = {"outcome": "abstained", "trace_id": "tr-abc",
              "tool_calls": [{"name": "prepare_leave_request", "status": "blocked", "duration_ms": 3}]}
    assert technical_details(result) == "Outcome: abstained · Trace: tr-abc"
    assert "prepare_leave_request" not in technical_details(result)  # tool names never reach the UI
    assert outcome_label("abstained").startswith("Tidak dijawab")
    assert outcome_label("something_new") == "something_new"


def test_leave_requests_are_readable_and_keep_the_raw_status() -> None:
    rows = leave_request_rows([{
        "request_id": "LR-HIST-010", "leave_type": "annual", "start_date": "2026-12-28", "end_date": "2026-12-29",
        "business_days": 2, "status": "pending_manager_review", "created_at": "2026-11-15T20:00:00+00:00",
    }])
    assert rows == [{
        "Nomor": "LR-HIST-010", "Jenis": "Cuti tahunan",
        "Tanggal": "Senin, 28 Desember 2026 – Selasa, 29 Desember 2026", "Hari kerja": 2,
        "Status": "Menunggu tinjauan manajer",
        "Diajukan": "Senin, 16 November 2026",  # 20:00 UTC on the 15th is already the 16th in WIB
        "Kode status": "pending_manager_review",
    }]


def test_error_messages_are_readable_and_keep_the_code() -> None:
    assert error_message(403, "Monitoring admin only") == \
        "Akses ditolak: menu ini hanya untuk peran yang berwenang. (API 403)"
    # A conflict already carries the right sentence from the API.
    assert error_message(409, "Proposal sudah kedaluwarsa (expired).") == "Proposal sudah kedaluwarsa (expired). (API 409)"


def test_alerts_become_table_rows() -> None:
    alert = {"rule_id": "agent-latency-p95", "metric": "p95_latency_ms", "value": 9020, "threshold": 8000,
             "samples": 34, "owner": "AI Platform", "response": "Inspect provider latency."}
    assert alert_rows([alert]) == [{"Alert": "agent-latency-p95", "Metrik": "p95_latency_ms", "Nilai": 9020,
                                     "Ambang": 8000, "Sampel": 34, "Pemilik": "AI Platform",
                                     "Tindakan": "Inspect provider latency."}]


@pytest.mark.parametrize("today", [
    date(2026, 11, 18),  # Wednesday: a week ahead is Wednesday the 25th, the next Monday is the 30th
    date(2026, 11, 22),  # Sunday
    date(2026, 11, 23),  # Monday: exactly a week ahead
])
def test_the_leave_example_is_always_a_future_monday_and_tuesday(today: date) -> None:
    leave = example_questions("EMP-001", today)[-1]
    assert leave == "Siapkan cuti tahunan 2026-11-30 sampai 2026-12-01"


def test_examples_follow_the_persona() -> None:
    today = date(2026, 11, 18)
    assert any("tim saya" in q for q in example_questions("EMP-010", today))
    assert not any("tim saya" in q for q in example_questions("EMP-001", today))  # employees get no team examples
    assert example_questions("ADM-001", today) == []