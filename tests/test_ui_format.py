"""The Streamlit client shows a leave proposal as readable text, not raw JSON."""
from __future__ import annotations

from datetime import date

import pytest

from ui_format import confirmation_message, long_date, proposal_markdown, status_label, wib_time

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
