"""Numbers in an answer must come from evidence the run actually saw."""
from __future__ import annotations

import pytest

from src.grounding import number_context_mismatches, numbers_in, unsupported_numbers

POLICY = "Pengajuan dilakukan paling lambat tiga hari kerja sebelum tanggal mulai."
# The real HR-LEAVE-001 sections (data/policies/annual-leave.md): three different facts, two of them in "hari kerja".
ANNUAL_LEAVE = [
    "Pegawai tetap memperoleh 12 hari kerja cuti tahunan per tahun kalender. Saldo tersedia pada sistem HR "
    "merupakan sumber operasional untuk pengajuan dan tidak boleh diganti dengan perhitungan model.",
    "Pengajuan dilakukan paling lambat tiga hari kerja sebelum tanggal mulai. Permintaan baru berstatus menunggu "
    "tinjauan manajer dan belum dianggap disetujui. Tanggal yang bertumpang tindih dengan permintaan aktif harus "
    "ditolak.",
    "Maksimal lima hari cuti dapat dibawa ke tahun berikutnya dan harus digunakan sebelum 31 Maret. Pengecualian "
    "memerlukan tiket HR dan persetujuan manusia.",
]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("paling lambat tiga hari kerja", {3}),
        ("dua belas hari; dua puluh satu; sepuluh; sebelas", {12, 21, 10, 11}),
        ("Maksimal 5 hari, sebelum 31 Maret.", {5, 31}),
        ("per 2026-11-12", {2026, 11, 12}),
        ("versi 2.1", {2.1}),  # a version is one number, so it never vouches for "2" or "1"
    ],
)
def test_numbers_are_read_as_values_digits_or_words(text: str, expected: set) -> None:
    assert numbers_in(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Lihat [HR-LEAVE-001#pengajuan] dan EMP-001, LR-HIST-001, AP-3f2a9c.",  # identifiers
        "1. Ajukan lewat asisten.\n2) Tunggu manajer.",  # the answer's own list numbering
        "Ini satu-satunya cara.",  # not a quantity
    ],
)
def test_identifiers_list_numbers_and_idioms_are_not_facts(text: str) -> None:
    assert numbers_in(text) == set()


def test_a_number_the_evidence_does_not_contain_is_reported() -> None:
    assert unsupported_numbers("Paling lambat 5 hari kerja [HR-LEAVE-001].", [POLICY]) == ["5"]


def test_the_same_number_in_digits_or_words_is_supported() -> None:
    assert unsupported_numbers("Paling lambat 3 hari kerja [HR-LEAVE-001].", [POLICY]) == []
    assert unsupported_numbers("Paling lambat tiga hari kerja.", ["paling lambat 3 hari kerja"]) == []


# --- The number must sit in a clause that resembles the policy clause carrying it ---

def test_a_number_swapped_between_two_facts_is_a_context_mismatch() -> None:
    """12 is a real number of this policy (the annual allowance), but the clause is about the notice period (3)."""
    answer = "Pengajuan paling lambat 12 hari kerja sebelum tanggal mulai. [HR-LEAVE-001]"
    assert unsupported_numbers(answer, ANNUAL_LEAVE) == []  # why the plain check is not enough
    assert number_context_mismatches(answer, ANNUAL_LEAVE, []) == ["12"]


@pytest.mark.parametrize(
    "answer",
    [
        "Pengajuan paling lambat 3 hari kerja sebelum tanggal mulai. [HR-LEAVE-001]",
        "Jatah cuti tahunan Anda 12 hari kerja per tahun. [HR-LEAVE-001]",
        "Anda berhak atas 12 hari per tahun kalender. [HR-LEAVE-001]",  # thin paraphrase: no sibling clause fits better
        "Maksimal 5 hari cuti dapat dibawa ke tahun berikutnya dan harus dipakai sebelum 31 Maret.",
        "Anda mendapat 12 hari cuti tahunan, dan pengajuan paling lambat tiga hari sebelum tanggal mulai.",
    ],
)
def test_correct_numbers_and_paraphrases_are_not_mismatches(answer: str) -> None:
    assert number_context_mismatches(answer, ANNUAL_LEAVE, []) == []


def test_a_number_the_user_wrote_is_not_judged_by_policy_context() -> None:
    answer = "Pengajuan paling lambat 12 hari kerja sebelum tanggal mulai."
    assert number_context_mismatches(answer, ANNUAL_LEAVE, ["Bisakah saya mengajukan 12 hari sebelumnya?"]) == []


def test_a_number_in_no_policy_clause_is_left_to_the_plain_check() -> None:
    answer = "Cuti tahunan 15 hari kerja."
    assert unsupported_numbers(answer, ANNUAL_LEAVE) == ["15"]
    assert number_context_mismatches(answer, ANNUAL_LEAVE, []) == []
