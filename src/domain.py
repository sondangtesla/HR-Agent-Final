"""Deterministic leave-domain rules; this module must never call the model."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from .contracts import LeaveBalance, PrepareLeaveArgs


class DomainError(ValueError):
    pass


# Indonesia has no daylight saving, so a fixed UTC+7 offset is exact and needs no tzdata.
WIB = timezone(timedelta(hours=7), "WIB")


def today_wib() -> date:
    return datetime.now(WIB).date()


# The rules in this module implement these policy versions. Stored with every proposal
# and request; tests/test_domain_rules.py fails if data/policies moves to a new version
# without this table (and the rules) being reviewed.
RULE_POLICY_VERSIONS = {
    "annual": "HR-LEAVE-001@2.1",
    "sick": "HR-LEAVE-002@1.4",
    "parental": "HR-LEAVE-003@1.2",
}

# Requests that still occupy their dates. Cancelled ones do not.
ACTIVE_STATUSES = frozenset({"pending_manager_review", "approved"})

# Messages are shown to employees, so they name the leave type in Indonesian, not the code.
LEAVE_TYPE_NAMES = {"annual": "tahunan", "sick": "sakit", "parental": "orang tua"}


def leave_type_name(leave_type: str) -> str:
    return LEAVE_TYPE_NAMES.get(leave_type, leave_type)


# Notice period: "paling lambat tiga hari kerja sebelum tanggal mulai" (data/policies/annual-leave.md).
# The submission day counts: submitted Wednesday -> earliest start is next Monday.
MIN_NOTICE_BUSINESS_DAYS = 3
NOTICE_RULE_LEAVE_TYPES = frozenset({"annual"})  # sick leave cannot be planned days ahead


def _is_business_day(day: date) -> bool:
    return day.weekday() < 5  # Monday=0 ... Friday=4


def _count_business_days(start: date, end: date) -> int:
    """Business days from start to end, both inclusive. 0 when end < start."""
    count, day = 0, start
    while day <= end:
        count += _is_business_day(day)
        day += timedelta(days=1)
    return count


def business_days(start: date, end: date) -> int:
    if end < start:
        raise DomainError("Tanggal selesai tidak boleh sebelum tanggal mulai.")
    days = _count_business_days(start, end)
    if days == 0:
        raise DomainError("Rentang tanggal tidak memuat hari kerja (hanya Sabtu/Minggu).")
    return days


def notice_business_days(today: date, start: date) -> int:
    """Business days from today (inclusive) up to the day before start."""
    return _count_business_days(today, start - timedelta(days=1))


def earliest_start_with_notice(today: date) -> date:
    """First business day that still leaves MIN_NOTICE_BUSINESS_DAYS of notice."""
    day = today
    while not (_is_business_day(day) and notice_business_days(today, day) >= MIN_NOTICE_BUSINESS_DAYS):
        day += timedelta(days=1)
    return day


def validate_leave_request(
    args: PrepareLeaveArgs,
    balances: list[LeaveBalance],
    overlaps: bool,
    today: date,
) -> tuple[int, list[str]]:
    """Check every rule in a fixed order and return (business days, summary).

    `balances` are the stored balances. They are already net of every confirmed
    request, so no pending days are subtracted here.

    Order matters, and the tests lock it:
    1. date order and 2. past date come before the 3-day rule (tests/test_domain.py:20);
    5. overlap comes before 6. balance (tests/test_domain.py:39-42).
    """
    start, end = args.start_date, args.end_date

    # 1. Date order
    if end < start:
        raise DomainError("Tanggal selesai tidak boleh sebelum tanggal mulai.")
    # 2. Past date
    if start < today:
        raise DomainError(f"Tanggal mulai {start.isoformat()} sudah lewat (masa lalu).")
    # 3. Business days in range
    days = business_days(start, end)
    # 4. Minimum notice (annual leave only)
    if args.leave_type in NOTICE_RULE_LEAVE_TYPES:
        notice = notice_business_days(today, start)
        if notice < MIN_NOTICE_BUSINESS_DAYS:
            earliest = earliest_start_with_notice(today)
            raise DomainError(
                f"Cuti tahunan harus diajukan paling lambat {MIN_NOTICE_BUSINESS_DAYS} hari kerja "
                f"sebelum tanggal mulai. Tanggal mulai paling cepat: {earliest.isoformat()}."
            )
    # 5. Overlap with an active request
    if overlaps:
        raise DomainError("Tanggal bertumpang tindih dengan permintaan cuti yang masih aktif.")
    # 6. Balance (already net of confirmed requests)
    balance = next((b for b in balances if b.leave_type == args.leave_type), None)
    if balance is None:
        raise DomainError(f"Saldo cuti {leave_type_name(args.leave_type)} tidak ditemukan.")
    if days > balance.available_days:
        raise DomainError(
            f"Saldo cuti {leave_type_name(args.leave_type)} tidak cukup: diminta {days} hari kerja, "
            f"tersedia {balance.available_days} hari."
        )

    summary = [
        f"Rentang {start.isoformat()} s.d. {end.isoformat()} berisi {days} hari kerja.",
        "Tidak ada tumpang tindih dengan permintaan aktif.",
        f"Saldo cuti {leave_type_name(args.leave_type)} cukup: tersedia {balance.available_days} hari, "
        f"sisa {balance.available_days - days} hari setelah pengajuan ini.",
    ]
    if args.leave_type in NOTICE_RULE_LEAVE_TYPES:
        summary.insert(1, f"Memenuhi batas pengajuan minimal {MIN_NOTICE_BUSINESS_DAYS} hari kerja.")
    return days, summary


# --- Leave action requests ---

# "Ajukan cuti tahunan 2025-01-02": a leave word, an action verb, and a date. Narrow on purpose:
# a policy question that mentions a date ("apakah 2026-12-24 libur?") is not an action request.
LEAVE_ACTION_VERBS = frozenset({
    "ajukan", "mengajukan", "diajukan", "siapkan", "menyiapkan", "buatkan", "ambil", "mengambil",
    "minta", "meminta", "request",
})
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def is_leave_action_request(message: str) -> bool:
    """True when the user asks the assistant to prepare a leave request for a given date.

    Used only to label the outcome honestly: if such a request ends without a proposal,
    nothing was done, whatever the model wrote instead.
    """
    words = set(_words(message))
    return "cuti" in words and bool(words & LEAVE_ACTION_VERBS) and bool(ISO_DATE.search(message))


# --- HR ticket rules ---

# Every word of the message must come from these two sets, and at least one must be a
# confirming word. Strict on purpose: "ya, tapi ganti kategorinya" or "ya kayaknya" is not a
# confirmation, and a user who types "yaa" simply has to type it again.
CONFIRMING_WORDS = frozenset({
    "ya", "iya", "yes", "ok", "oke", "okay", "confirm", "konfirmasi", "setuju",
    "kirim", "kirimkan", "benar", "betul", "lanjut", "lanjutkan",
})
CONFIRMATION_FILLERS = frozenset({
    "saja", "aja", "deh", "dong", "sekarang", "silakan", "tolong", "saya", "sudah",
    "tiket", "tiketnya", "itu", "please",
})
MAX_CONFIRMATION_WORDS = 6

# Words that say "I want a ticket" without saying what it is about.
GENERIC_TICKET_WORDS = frozenset({
    "tiket", "ticket", "hr", "buat", "buatkan", "membuat", "dibuat", "tolong", "bantu", "bantuan",
    "membantu", "mohon", "please", "help", "saya", "aku", "mau", "ingin", "minta", "meminta",
    "pengguna", "user", "karyawan", "pegawai", "ada", "masalah", "pertanyaan", "soal", "tentang",
    "terkait", "mengenai", "untuk", "ke", "dan", "yang", "di", "dengan", "ini", "itu", "test",
    "tes", "testing", "coba", "umum", "lain", "lainnya", "perlu", "butuh", "request", "ajukan",
    "mengajukan", "kirim", "data",
})
MIN_TICKET_SUMMARY_CHARS = 15
MIN_TICKET_CONTENT_WORDS = 2


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def is_explicit_confirmation(message: str) -> bool:
    """True only when the WHOLE message is a short, unambiguous yes ("ya", "ya kirim", "confirm").

    Decided by code, never by the model: text like "user sudah setuju" in a message can fool a
    model, but it is not a confirmation here because it is more than a plain yes.
    """
    if "?" in message:  # "ok?" is a question, not an answer
        return False
    words = _words(message)
    if not words or len(words) > MAX_CONFIRMATION_WORDS:
        return False
    allowed = CONFIRMING_WORDS | CONFIRMATION_FILLERS
    return all(word in allowed for word in words) and any(word in CONFIRMING_WORDS for word in words)


def ticket_summary_problem(summary: str) -> str | None:
    """Why a ticket summary is not complete enough to send to HR, or None when it is."""
    content = [word for word in _words(summary) if word not in GENERIC_TICKET_WORDS and len(word) > 1]
    if len(summary.strip()) < MIN_TICKET_SUMMARY_CHARS or len(content) < MIN_TICKET_CONTENT_WORDS:
        return (
            "Ringkasan tiket belum menjelaskan masalahnya. Tanyakan kepada pengguna apa yang perlu "
            "ditangani HR (misalnya data yang salah, pengecualian yang diminta, atau pertanyaan yang "
            "belum terjawab), lalu panggil create_hr_ticket lagi dengan ringkasan dari jawabannya. "
            "Jangan mengarang ringkasan."
        )
    return None


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    input_rate: float | None,
    output_rate: float | None,
) -> float | None:
    """Cost in the rate's currency. Rates are per 1M tokens and come from the instructor."""
    if input_rate is None or output_rate is None:
        return None
    return round((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 6)
