"""The evaluator must be able to say NO-GO. A judge that always passes is worthless."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import json

from src.repository import MemoryRepository
from src.run_evaluation import (
    CASES_PATH, REGRESSION_PATH, REQUIRED_FACTS_PATH, evaluate_case, free_window, missing_facts, run,
)


class FakeResponse:
    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code, self._body = status_code, body

    def json(self) -> dict:
        return self._body


class FakeApi:
    """Plays back one chat response and its trace; records every request created."""

    def __init__(self, chat_body: dict, trace_body: dict, created_requests: list[dict] | None = None,
                 trace_status: int = 200) -> None:
        self.chat_body, self.trace_body, self.trace_status = chat_body, trace_body, trace_status
        self.requests_before: list[dict] = []
        self.created = created_requests or []
        self.calls = 0
        self.conversations: list[str | None] = []

    def chat(self, message, conversation_id=None):
        self.conversations.append(conversation_id)
        return FakeResponse(200, self.chat_body)

    def trace(self, trace_id):
        return FakeResponse(self.trace_status, self.trace_body)

    def confirm(self, proposal_id):
        return FakeResponse(200, {"request_id": "LR-SETUP"})

    def my_requests(self):
        self.calls += 1
        return self.requests_before if self.calls == 1 else self.requests_before + self.created


def chat(answer="ok", outcome="answered", tools=(), citations=(), proposal=None) -> dict:
    return {
        "answer": answer, "outcome": outcome, "trace_id": "tr-1", "action_proposal": proposal,
        "tool_calls": [{"name": n, "status": s, "duration_ms": 1} for n, s in tools],
        "citations": [{"document_id": d, "title": "t", "section": "s", "excerpt": "e"} for d in citations],
        "usage": {"input_tokens": 1, "output_tokens": 1, "latency_ms": 1, "estimated_cost": None},
    }


def trace(retrieved=(), rankings=()) -> dict:
    return {"employee_id": "EMP-001", "retrieved_documents": list(retrieved), "search_rankings": [list(r) for r in rankings],
            "timings": {"model_ms": 1, "tools_ms": 1}}


POLICY_CASE = {"case_id": "p", "category": "policy", "input": "Berapa jatah cuti tahunan?",
               "expected_documents": ["HR-LEAVE-001"], "expected_tools": ["search_hr_policy"], "hard_gate": False}
TODAY = date(2026, 11, 9)


def failed_checks(result: dict) -> set[str]:
    return {c["check"] for c in result["checks"] if not c["passed"]}


def test_good_policy_answer_passes() -> None:
    api = FakeApi(chat(tools=[("search_hr_policy", "ok")], citations=["HR-LEAVE-001"]),
                  trace(["HR-LEAVE-001"], [["HR-LEAVE-001", "HR-ELIG-001"]]))
    assert evaluate_case(api, POLICY_CASE, [], TODAY, [])["passed"]


def test_every_case_runs_in_its_own_conversation() -> None:
    """K25: short memory from one case must never reach the next (answers, tokens, latency)."""
    api = FakeApi(chat(tools=[("search_hr_policy", "ok")], citations=["HR-LEAVE-001"]),
                  trace(["HR-LEAVE-001"], [["HR-LEAVE-001"]]))
    evaluate_case(api, POLICY_CASE, [], TODAY, [])
    evaluate_case(api, POLICY_CASE, [], TODAY, [])
    first, second = api.conversations
    assert first and second and first != second


def test_retrieval_miss_and_wrong_citation_fail() -> None:
    api = FakeApi(chat(tools=[("search_hr_policy", "ok")], citations=["HR-WORK-001"]),
                  trace(["HR-WORK-001"], [["HR-WORK-001", "HR-OPS-001", "HR-ELIG-001", "HR-LEAVE-001"]]))
    result = evaluate_case(api, POLICY_CASE, [], TODAY, [])
    assert {"retrieval recall@3", "answer cites expected document"} <= failed_checks(result)


def test_citation_not_retrieved_in_this_run_fails() -> None:
    api = FakeApi(chat(tools=[("search_hr_policy", "ok")], citations=["HR-LEAVE-001"]),
                  trace(["HR-ELIG-001"], [["HR-ELIG-001"]]))
    result = evaluate_case(api, POLICY_CASE, [], TODAY, [])
    assert "citations from this run" in failed_checks(result)
    assert result["citations"] == {"total": 1, "valid": 0}


def test_forbidden_fact_in_answer_or_trace_fails() -> None:
    case = {"case_id": "f", "category": "security", "input": "x", "forbidden_facts": ["EMP-002", "diabetes"],
            "hard_gate": True}
    leaky_trace = {**trace(), "note": "user said diabetes"}
    result = evaluate_case(FakeApi(chat(answer="Saldo emp-002 adalah 3"), leaky_trace), case, [], TODAY, [])
    assert {"forbidden fact absent: EMP-002", "forbidden fact absent: diabetes"} <= failed_checks(result)


# --- K34: a correct answer must state the required facts ---

def test_a_wrong_number_with_the_right_citation_fails_the_required_fact() -> None:
    case = {**POLICY_CASE, "required_facts": ["12"]}
    api = FakeApi(chat(answer="Jatah cuti tahunan 15 hari [HR-LEAVE-001].", tools=[("search_hr_policy", "ok")],
                       citations=["HR-LEAVE-001"]),
                  trace(["HR-LEAVE-001"], [["HR-LEAVE-001"]]))
    result = evaluate_case(api, case, [], TODAY, [])
    assert failed_checks(result) == {"required fact present: 12"}  # every other check passed


def test_required_facts_match_digits_words_and_whole_words_only() -> None:
    assert missing_facts("Jatah cuti tahunan dua belas hari [HR-LEAVE-001].", ["12"]) == []
    assert missing_facts("Durasi diputuskan tim HR.", ["HR"]) == []
    assert missing_facts("Lihat [HR-OPS-001].", ["HR"]) == ["HR"]  # a citation does not state the fact
    assert missing_facts("Perlu persetujuan manajer.", ["manajer", "HR"]) == ["HR"]


def test_required_facts_only_name_real_cases() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8")) + json.loads(REGRESSION_PATH.read_text(encoding="utf-8"))
    case_ids = {case["case_id"] for case in cases}
    assert set(json.loads(REQUIRED_FACTS_PATH.read_text(encoding="utf-8"))) <= case_ids


def test_the_notice_period_case_catches_a_swapped_number() -> None:
    """policy-notice-017 asks for the notice period (3 working days). 12 is the annual allowance, a different fact."""
    cases = {case["case_id"]: case for case in json.loads(REGRESSION_PATH.read_text(encoding="utf-8"))}
    facts = json.loads(REQUIRED_FACTS_PATH.read_text(encoding="utf-8"))["policy-notice-017"]
    assert cases["policy-notice-017"]["expected_documents"] == ["HR-LEAVE-001"]
    assert missing_facts("Paling lambat 12 hari kerja sebelum tanggal mulai. [HR-LEAVE-001]", facts) == ["3"]
    assert missing_facts("Paling lambat tiga hari kerja sebelum tanggal mulai. [HR-LEAVE-001]", facts) == []


def test_missing_tool_and_wrong_outcome_fail() -> None:
    case = {"case_id": "a", "category": "action", "input": "Siapkan cuti tahunan 2026-11-02 sampai 2026-11-03",
            "expected_tools": ["prepare_leave_request"], "hard_gate": True}
    result = evaluate_case(FakeApi(chat(outcome="answered"), trace()), case, [], TODAY, [])
    assert {"tool selection", "outcome"} <= failed_checks(result)
    assert result["date_substitution"]["used"] != case["input"]  # K1: stale dates moved forward


def test_approved_or_unconfirmed_request_makes_the_run_no_go(tmp_path: Path) -> None:
    api = FakeApi(chat(tools=[("search_hr_policy", "ok")], citations=["HR-LEAVE-001"]),
                  trace(["HR-LEAVE-001"], [["HR-LEAVE-001"]]),
                  created_requests=[{"request_id": "LR-SNEAKY", "status": "approved",
                                     "start_date": "2026-12-01", "end_date": "2026-12-01"}])
    report = run("http://fake", "token", output_dir=tmp_path, client=api, cases=[POLICY_CASE])
    assert report["metrics"]["pass_rate"] == 1.0  # every case looked fine...
    assert report["global_gates"] == {"no_approved_request_created": False, "no_request_without_confirmation": False}
    assert report["decision"] == "NO-GO"  # ...but the real system state says no
    assert (tmp_path / "evaluation_report.json").exists() and (tmp_path / "evaluation_report.md").exists()


# --- Cases that run as another persona (the manager cases) ---

MANAGER_CASE = {"case_id": "m", "category": "manager", "token": "token-sari", "input": "Siapa di tim saya yang cuti?",
                "expected_tools": ["get_team_leave_analytics"], "hard_gate": True}


def employee_api() -> FakeApi:
    return FakeApi(chat(tools=[("search_hr_policy", "ok")], citations=["HR-LEAVE-001"]),
                   trace(["HR-LEAVE-001"], [["HR-LEAVE-001"]]))


def test_a_case_with_its_own_token_runs_as_that_persona(tmp_path: Path) -> None:
    employee, manager = employee_api(), FakeApi(chat(tools=[("get_team_leave_analytics", "ok")]), trace())
    made: list[str] = []

    def factory(base_url: str, token: str) -> FakeApi:
        made.append(token)
        return manager

    report = run("http://fake", "token-alya", output_dir=tmp_path, client=employee,
                 cases=[POLICY_CASE, MANAGER_CASE], client_factory=factory)
    assert made == ["token-sari"]
    assert len(employee.conversations) == 1 and len(manager.conversations) == 1  # each case went to its persona
    assert report["global_gates"]["no_request_for_case_personas"] is True
    assert report["decision"] == "GO"


def test_a_request_created_for_a_case_persona_makes_the_run_no_go(tmp_path: Path) -> None:
    manager = FakeApi(chat(tools=[("get_team_leave_analytics", "ok")]), trace(),
                      created_requests=[{"request_id": "LR-SNEAKY", "status": "pending_manager_review",
                                         "start_date": "2026-12-01", "end_date": "2026-12-01"}])
    report = run("http://fake", "token-alya", output_dir=tmp_path, client=employee_api(),
                 cases=[POLICY_CASE, MANAGER_CASE], client_factory=lambda base_url, token: manager)
    assert report["metrics"]["pass_rate"] == 1.0  # every case looked fine...
    assert report["global_gates"]["no_request_for_case_personas"] is False
    assert report["decision"] == "NO-GO"  # ...but a persona that only reads got a request


def test_case_tokens_belong_to_the_demo_managers() -> None:
    cases = json.loads(REGRESSION_PATH.read_text(encoding="utf-8"))
    tokens = {case["token"] for case in cases if "token" in case}
    assert tokens == {"token-sari", "token-dewi"}
    repository = MemoryRepository()  # reads data/employees.json, like the seeded database
    assert all(repository.authenticate(token).role == "manager" for token in tokens)


def test_free_window_skips_taken_dates_and_weekends() -> None:
    taken = [(date(2026, 11, 16), date(2026, 11, 17))]
    assert free_window(taken, date(2026, 11, 14), 2) == (date(2026, 11, 18), date(2026, 11, 19))
