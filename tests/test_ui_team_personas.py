"""Manager personas live in their own file, so the supplied demo_personas.json stays untouched."""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.repository import MemoryRepository
from ui_contract import load_personas

ROOT = Path(__file__).resolve().parents[1]


def test_team_personas_are_managers_with_their_own_tokens() -> None:
    supplied = load_personas(ROOT / "demo_personas.json")
    team = load_personas(ROOT / "demo_personas_team.json")
    assert {item["employee_id"] for item in team} == {"EMP-010", "EMP-020"}
    tokens = [item["demo_token"] for item in supplied + team]
    assert len(set(tokens)) == len(tokens)  # no persona can log in as another one

    repository = MemoryRepository()  # reads data/employees.json, like the seeded database
    for item in team:
        identity = repository.authenticate(item["demo_token"])
        assert identity.employee_id == item["employee_id"] and identity.role == "manager"


def test_supplied_ui_lists_the_supplied_personas_first_then_the_managers() -> None:
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert list(app.sidebar.selectbox[0].options) == [
        "Alya — pegawai", "Bima — pegawai", "Monitoring admin",
        "Sari — manajer Engineering", "Dewi — manajer Finance",
    ]
