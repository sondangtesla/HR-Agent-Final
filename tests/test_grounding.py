"""K34: numbers in an answer must come from evidence the run actually saw."""
from __future__ import annotations

import pytest

from src.grounding import numbers_in, unsupported_numbers

POLICY = "Pengajuan dilakukan paling lambat tiga hari kerja sebelum tanggal mulai."


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
