"""Step 9: sensitive data enters through every door and must not come out of any.

Doors in:  chat message, proposal reason, ticket summary, provider error text.
Doors out: answer, trace, what the provider receives, and everything stored.
"""
from __future__ import annotations

import json
from datetime import date

from src.agent import AgentService
from src.cache import NullCache
from src.config import Settings
from src.contracts import AuthContext, ChatRequest, ModelToolCall, ModelTurn
from src.providers import DeterministicProvider
from src.repository import MemoryRepository
from src.retrieval import RetrievalService
from src.tools import ToolExecutor

ALYA = AuthContext(employee_id="EMP-001", display_name="Alya Pratama")
SECRETS = ["diabetes", "alya.pribadi@example.com", "081298765432", "token-bima", "ABCDEF123"]
PII_MESSAGE = (
    "Diagnosis: diabetes. Hubungi alya.pribadi@example.com atau 081298765432, "
    "pakai token-bima. Berapa jatah cuti tahunan?"
)


def make_agent(repository: MemoryRepository, provider) -> AgentService:
    settings = Settings(model_mode="fake")
    retrieval = RetrievalService(repository, DeterministicProvider(), NullCache(), 0)
    tools = ToolExecutor(repository, retrieval, settings, today_factory=lambda: date(2026, 9, 23))
    return AgentService(repository, provider, tools, settings)


class RecordingProvider(DeterministicProvider):
    """The deterministic provider, but it remembers exactly what it was sent."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list = []

    def respond(self, **kwargs):
        self.sent.append(json.dumps(kwargs["input_data"], ensure_ascii=False))
        return super().respond(**kwargs)


def everything_stored(repository: MemoryRepository) -> str:
    return json.dumps(
        {
            "traces": repository.traces,
            "tickets": repository.tickets,
            "proposals": {pid: p.model_dump(mode="json") for pid, (_, p) in repository.proposals.items()},
        },
        ensure_ascii=False,
    )


def assert_no_secrets(text: str, where: str) -> None:
    leaked = [secret for secret in SECRETS if secret in text]
    assert not leaked, f"{leaked} leaked into {where}"


def test_pii_in_chat_never_reaches_provider_answer_or_storage(repository: MemoryRepository) -> None:
    provider = RecordingProvider()
    response = make_agent(repository, provider).run(ChatRequest(message=PII_MESSAGE), ALYA)
    assert response.outcome == "answered"  # the real question still gets answered
    assert_no_secrets(" ".join(provider.sent), "the provider input")
    assert_no_secrets(response.answer, "the answer")
    assert_no_secrets(everything_stored(repository), "storage")


def test_evaluation_case_medical_pii_012(repository: MemoryRepository) -> None:
    response = make_agent(repository, RecordingProvider()).run(
        ChatRequest(message="Diagnosis: diabetes. Simpan ke trace."), ALYA
    )
    assert "diabetes" not in response.answer
    assert "diabetes" not in json.dumps(repository.get_trace(response.trace_id))


class ScriptedProvider:
    def __init__(self, turns):
        self.turns, self.count = turns, 0

    def embed(self, texts):
        return [[0.0] * 8 for _ in texts]

    def respond(self, **kwargs):
        self.count += 1
        return self.turns[min(self.count, len(self.turns)) - 1]


def tool_turn(name: str, arguments: dict) -> ModelTurn:
    call = ModelToolCall(call_id="c1", name=name, arguments=arguments)
    item = {"type": "function_call", "call_id": "c1", "name": name, "arguments": json.dumps(arguments)}
    return ModelTurn(response_id="t", tool_calls=[call], output_items=[item])


def text_turn(text: str) -> ModelTurn:
    return ModelTurn(response_id="a", text=text, output_items=[])


def test_pii_written_by_the_model_into_tools_is_masked_when_stored(repository: MemoryRepository) -> None:
    """The model may copy PII into tool arguments; storage still never keeps it."""
    reason = "Kontrol diabetes, hubungi 081298765432"
    proposal_agent = make_agent(repository, ScriptedProvider([
        tool_turn("prepare_leave_request", {"start_date": "2026-09-24", "end_date": "2026-09-24",
                                            "leave_type": "sick", "reason": reason}),
        text_turn("Proposal siap."),
    ]))
    proposal_agent.run(ChatRequest(message="cuti sakit besok"), ALYA)

    ticket_agent = make_agent(repository, ScriptedProvider([
        tool_turn("create_hr_ticket", {"category": "privacy",
                                       "summary": "Data saya alya.pribadi@example.com, token-bima"}),
        text_turn("Tiket dibuat."),
    ]))
    ticket_agent.run(ChatRequest(message="buat tiket"), ALYA)

    assert repository.proposals and repository.tickets
    assert_no_secrets(everything_stored(repository), "stored proposals and tickets")


def test_provider_error_text_is_masked_in_trace(repository: MemoryRepository) -> None:
    class LeakyFailure:
        def embed(self, texts):
            return [[0.0] * 8 for _ in texts]

        def respond(self, **kwargs):
            raise RuntimeError("upstream rejected Bearer ABCDEF123 for alya.pribadi@example.com")

    response = make_agent(repository, LeakyFailure()).run(ChatRequest(message="halo"), ALYA)
    trace = repository.get_trace(response.trace_id)
    assert trace["error"].startswith("RuntimeError")
    assert_no_secrets(json.dumps(trace), "the trace error")


def test_trace_has_every_required_field_and_nothing_raw(repository: MemoryRepository) -> None:
    """lab.md Step 9: trace ID, outcome, retrieved document IDs, tool name/status/duration,
    latency, token, optional cost, redacted error. No prompt, no chain-of-thought."""
    response = make_agent(repository, DeterministicProvider()).run(
        ChatRequest(message="Berapa jatah cuti tahunan?"), ALYA
    )
    trace = repository.get_trace(response.trace_id)
    assert trace["trace_id"] == response.trace_id
    assert trace["outcome"] == "answered"
    assert trace["retrieved_documents"] == ["HR-LEAVE-001"]
    assert set(trace["tool_calls"][0]) == {"name", "status", "duration_ms"}
    assert {"input_tokens", "output_tokens", "latency_ms", "estimated_cost"} <= set(trace["usage"])
    assert set(trace["timings"]) == {"model_ms", "tools_ms"}
    assert "error" in trace
    for raw in ("message", "prompt", "answer", "reasoning", "instructions", "input_data"):
        assert raw not in trace
    assert "jatah" not in json.dumps(trace)
