"""Numbers in an answer must come from this run's evidence.

Citation validation proves WHICH document an answer used, not WHAT it says: "Cuti tahunan
15 hari [HR-LEAVE-001]" passes it although the document says 12. HR answers go wrong in their
numbers (days, dates, limits), so every number the model writes must appear in something this run
actually saw: the user's message, the short memory, today's date, or a tool output. A number that
appears nowhere was made up or calculated by the model, which HR-LEAVE-001 forbids ("tidak boleh
diganti dengan perhitungan model").
"""
from __future__ import annotations

import re

_UNITS = {"satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6, "tujuh": 7, "delapan": 8,
          "sembilan": 9}
_UNIT = "|".join(_UNITS)
# Policies write some numbers as words ("tiga hari kerja"); the model may write them as digits.
_TENS = re.compile(rf"\b({_UNIT})\s+puluh(?:\s+({_UNIT}))?\b(?!-)")
_TEENS = re.compile(rf"\b({_UNIT})\s+belas\b(?!-)")
_SINGLE = re.compile(rf"\b(sepuluh|sebelas|{_UNIT})\b(?!-)")  # (?!-): "satu-satunya" is not a number
# Identifiers carry digits that are not facts: HR-LEAVE-001, EMP-001, LR-HIST-001, AP-3f2a9c.
_IDENTIFIER = re.compile(r"\b[A-Za-z]+(?:-[A-Za-z0-9]+)+\b")
_LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)]\s+")  # "1. ..." numbering of the answer itself
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")  # "2.1" stays one number, "2026-11-12" is three


def without_identifiers(text: str) -> str:
    """The text without IDs such as [HR-LEAVE-001] or EMP-001, which are not stated facts."""
    return _IDENTIFIER.sub(" ", text)


def numbers_in(text: str) -> set[float]:
    """Every number stated in `text`, words included: "dua belas hari" -> {12}."""
    text = _LIST_MARKER.sub("", without_identifiers(text)).lower()
    text = _TENS.sub(lambda m: str(_UNITS[m[1]] * 10 + (_UNITS[m[2]] if m[2] else 0)), text)
    text = _TEENS.sub(lambda m: str(10 + _UNITS[m[1]]), text)
    text = _SINGLE.sub(lambda m: str({"sepuluh": 10, "sebelas": 11}.get(m[1]) or _UNITS[m[1]]), text)
    return {float(token.replace(",", ".")) for token in _NUMBER.findall(text)}


def unsupported_numbers(answer: str, evidence: list[str]) -> list[str]:
    """Numbers in the answer that appear in none of the evidence, e.g. ["15"]."""
    known: set[float] = set()
    for text in evidence:
        known |= numbers_in(text)
    return sorted(f"{n:g}" for n in numbers_in(answer) - known)



# --- Context: a number must sit in a clause that resembles the policy clause carrying it ---
# unsupported_numbers() only asks "does this number appear anywhere?". "Pengajuan paling lambat 12 hari kerja"
# passes it, because 12 is in the policy, as the annual allowance and not as the notice period (3).
_WORD = re.compile(r"[a-z]{3,}")
_CLAUSE_SPLIT = re.compile(r"(?<=[.;!?,])\s+|\n+")
# Words many clauses share say nothing about WHICH fact a clause states: connectors, units, number words.
_COMMON = frozenset(
    "yang dan atau dari untuk dengan pada dalam oleh adalah akan dapat harus boleh tidak anda saya kami bagi "
    "sebagai ini itu per hari kerja tahun bulan minggu puluh belas sepuluh sebelas".split()
) | frozenset(_UNITS)


def _clauses(text: str) -> list[str]:
    return [clause for clause in _CLAUSE_SPLIT.split(without_identifiers(text)) if clause.strip()]


def _topic_words(clause: str) -> set[str]:
    return set(_WORD.findall(clause.lower())) - _COMMON


def number_context_mismatches(answer: str, policy_texts: list[str], user_texts: list[str]) -> list[str]:
    """Numbers whose answer clause resembles a policy clause of ANOTHER fact more than the one carrying them.

    Only numbers found in the policy text are judged: a number in no policy clause is the plain check's job,
    and a number the user wrote is theirs. Meant for shadow mode first: paraphrases can trigger false alarms.
    """
    from_user = set().union(*(numbers_in(text) for text in user_texts)) if user_texts else set()
    policy = [(numbers_in(clause), _topic_words(clause)) for text in policy_texts for clause in _clauses(text)]
    flagged: set[float] = set()
    for clause in _clauses(answer):
        words = _topic_words(clause)
        for number in numbers_in(clause) - from_user:
            own = [len(words & topic) for numbers, topic in policy if number in numbers]
            if not own:
                continue
            foreign = [len(words & topic) for numbers, topic in policy if number not in numbers]
            if max(foreign, default=0) > max(own):
                flagged.add(number)
    return sorted(f"{n:g}" for n in flagged)