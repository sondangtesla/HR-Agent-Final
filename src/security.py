"""Security helpers. Complete every TODO before persisting telemetry."""
from __future__ import annotations

import hashlib
import re


def token_hash(token: str) -> str:
    """Return a deterministic SHA-256 hex digest so the raw token is never stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


SAFETY_ID_NAMESPACE = "hr-assistant/safety-identifier/v1:"


def stable_safety_id(employee_id: str) -> str:
    """Stable pseudonym for the provider's safety_identifier.

    Same employee -> same ID in every process, so the provider can spot abuse by one user,
    but it never sees "EMP-001". The namespace keeps it different from any other hash of
    the same ID. 6 + 32 characters stays under the provider's 64-character limit.
    """
    digest = hashlib.sha256((SAFETY_ID_NAMESPACE + employee_id).encode("utf-8")).hexdigest()
    return "hrsid_" + digest[:32]


# Each pattern is narrow on purpose: redaction that hides dates, employee IDs, or the word
# "sakit" would make traces useless. Patterns run in this order.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")

# key=value or key: value secrets, e.g. "api_key=abc", "password: hunter2"
_KEY_VALUE_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|password|passwd|secret|token)(\s*[:=]\s*)[^\s,;]+"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
# Token-shaped words need a - or _ right after the prefix ("token-alya", "sk-abc123",
# "secret_x1"), so prose like "token pegawai lain" is left alone.
_TOKEN_LIKE = re.compile(r"(?i)\b(?:token|secret|sk)[-_][A-Za-z0-9_-]{3,}")

# Indonesian mobile numbers only: 08xx / 628xx / +62 8xx, 9-13 digits after the prefix.
# A bare long number (e.g. 1234567890) or a date (2026-11-02) does not match.
_PHONE = re.compile(r"(?<![\w+])(?:\+62[\s-]?|62|0)8\d(?:[\s.-]?\d){7,11}(?!\d)")

# Medical detail after a word that introduces a diagnosis: "diagnosis: diabetes.", "menderita GERD".
# The mask stops at the end of that part of the sentence: . ; , new line, or a word that starts
# the request. "didiagnosis hipertensi, jadi mau cuti 2026-11-12" keeps "jadi mau cuti 2026-11-12",
# so the leave request and its date still reach the agent (K33).
_MEDICAL_TRIGGERS = (
    r"diagnosis|diagnosa|didiagnosis|didiagnosa|penyakit(?:nya)?|riwayat medis|kondisi medis|hasil lab|"
    r"menderita|mengidap|terjangkit"
)
_REQUEST_START = r"jadi|sehingga|maka|mohon|tolong|mau|ingin|minta|dan\s+saya"
_MEDICAL_AFTER_TRIGGER = re.compile(
    rf"(?i)\b({_MEDICAL_TRIGGERS})(\s*[:=-]?\s*)(?:(?!\s*\b(?:{_REQUEST_START})\b)[^.,;\n])+"
)
# Condition names that are sensitive on their own. "sakit" is NOT here: "cuti sakit" is a leave type.
# A list is never complete: an unlisted condition without a trigger word still passes (R-010).
_MEDICAL_TERMS = re.compile(
    r"(?i)\b(diabetes|hipertensi|kanker|asma|tbc|tuberkulosis|hiv|aids|hepatitis|covid(?:-19)?|"
    r"depresi|bipolar|skizofrenia|stroke|epilepsi|demam berdarah|dbd|tifus|tipes|migrain|"
    r"gagal ginjal|serangan jantung|"
    # K33
    r"vertigo|gerd|maag|asam lambung|asam urat|kolesterol|anemia|tifoid|sinusitis|bronkitis|"
    r"pneumonia|cacar|campak|kista|tumor|usus buntu|patah tulang|gegar otak|insomnia|hernia|"
    r"osteoporosis|katarak|glaukoma|leukemia|lupus|gangguan kecemasan|gangguan mental|gangguan jiwa|"
    r"serangan panik)\b"
)
# Symptoms named by body part: "sakit kepala", "radang tenggorokan". "sakit" alone stays readable.
_BODY_SYMPTOM = re.compile(
    r"(?i)\b(?:sakit|nyeri|radang|infeksi)\s+(?:kepala|perut|gigi|punggung|pinggang|dada|tenggorokan|"
    r"mata|telinga|jantung|ginjal|lambung|kulit|sendi|lutut|leher|paru(?:-paru)?|saluran\s+kemih)\b"
)


def redact(value: str) -> str:
    """Mask email, Indonesian phone numbers, token-like values, and medical detail."""
    value = _EMAIL.sub("[EMAIL]", value)
    value = _KEY_VALUE_SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}[TOKEN]", value)
    value = _BEARER.sub("Bearer [TOKEN]", value)
    value = _TOKEN_LIKE.sub("[TOKEN]", value)
    value = _PHONE.sub("[TELEPON]", value)
    value = _MEDICAL_AFTER_TRIGGER.sub(lambda m: f"{m.group(1)}{m.group(2)}[MEDIS]", value)
    value = _MEDICAL_TERMS.sub("[MEDIS]", value)
    value = _BODY_SYMPTOM.sub("[MEDIS]", value)
    return value
