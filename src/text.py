"""Small text helpers shared by retrieval, the repositories, and the fake provider."""
from __future__ import annotations

import re

# Question words and fillers that carry no policy meaning. Kept short on purpose:
# a word wrongly listed here can never be found by lexical search.
STOPWORDS = frozenset(
    {
        "apa", "apakah", "bagaimana", "berapa", "kapan", "siapa", "mana", "mengapa", "kenapa",
        "yang", "dan", "atau", "di", "ke", "dari", "untuk", "dengan", "pada", "ini", "itu",
        "saya", "aku", "kami", "saat", "jika", "bisa", "ada", "per",
    }
)

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens without stopwords, in order, without duplicates.

    Only [a-z0-9] survives, so a token can never carry tsquery operators like ! & | ( ).
    """
    seen: dict[str, None] = {}
    for token in TOKEN_PATTERN.findall(text.lower()):
        if token not in STOPWORDS:
            seen.setdefault(token, None)
    return list(seen)
