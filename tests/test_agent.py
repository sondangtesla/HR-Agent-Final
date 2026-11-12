"""Agent loop limits, citation rules, output guard, and trace privacy."""
from __future__ import annotations

import json
import time
from datetime import date

from src.agent import AgentService
from src.cache import MemoryCache, NullCache
from src.config import Settings
from src.contracts import AuthContext, ChatRequest, ModelToolCall, ModelTurn
from src.conversation import ConversationStore
from src.providers import DeterministicProvider
from src.repository import MemoryRepository
from src.retrieval import RetrievalService
from src.security import stable_safety_id
from src.tools import TOOL_SCHEMAS, ToolExecutor

ALYA = AuthContext(employee_id="EMP-001", display_name="Alya Pratama")


def make_agent(repository: MemoryRepository, provider, **overrides) -> AgentService:
    settings = Settings(model_mode="fake", **overrides)
    retrieval = RetrievalService(repository, DeterministicProvider(), NullCache(), 0)
    tools = ToolExecutor(repository, retrieval, settings, today_factory=lambda: date(2026, 9, 23))
    return AgentService(repository, provider, tools, settings)


def search_call(call_id: str = "c1") -> ModelToolCall:
    return ModelToolCall(call_id=call_id, name="search_hr_policy", arguments={"query": "cuti tahunan", "top_k": 3})


def as_items(calls: list[ModelToolCall]) -> list[dict]:
    return [{"type": "function_call", "call_id": c.call_id, "name": c.name, "arguments": json.dumps(c.arguments)}
            for c in calls]


class ScriptedProvider:
    """Plays back a list of turns and records every respond() call."""

    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = turns
        self.calls: list[dict] = []

    def embed(self, texts):
        return [[0.0] * 8 for _ in texts]

    def respond(self, **kwargs):
        self.calls.append(kwargs)
        return self.turns[min(len(self.calls), len(self.turns)) - 1]


def tool_turn(calls: list[ModelToolCall]) -> ModelTurn:
    return ModelTurn(response_id="t", tool_calls=calls, output_items=as_items(calls))


def text_turn(text: str) -> ModelTurn:
    return ModelTurn(response_id="a", text=text, output_items=[{"type": "message", "role": "assistant",
                                                                 "content": [{"type": "output_text", "text": text}]}])


# --- Limits ---

def test_turn_limit_stops_a_model_that_never_answers(repository: MemoryRepository) -> None:
    provider = ScriptedProvider([tool_turn([search_call()])])  # asks for a tool forever
    response = make_agent(repository, provider).run(ChatRequest(message="cuti"), ALYA)
    assert len(provider.calls) == 4
    assert response.outcome == "abstained"
    assert repository.get_trace(response.trace_id)["stop_reason"] == "turn_limit"


def test_tool_call_limit_runs_six_then_lets_the_model_answer(repository: MemoryRepository) -> None:
    """K30, "continue" mode: six calls run, the seventh is refused, and the model may still answer."""
    seven = [search_call(f"c{i}") for i in range(7)]
    provider = ScriptedProvider([tool_turn(seven), text_turn("Hak cuti 12 hari. [HR-LEAVE-001]")])
    response = make_agent(repository, provider).run(ChatRequest(message="cuti"), ALYA)
    assert len(response.tool_calls) == 6  # only six reached our tools
    assert len(provider.calls) == 2  # the model got one more turn after the limit
    refused = [item for item in provider.calls[1]["input_data"]
               if item.get("type") == "function_call_output" and item.get("call_id") == "c6"]
    assert refused and "limit" in refused[0]["output"].lower()
    assert response.outcome == "answered"
    trace = repository.get_trace(response.trace_id)
    assert trace["tool_limit_reached"] is True
    assert trace["stop_reason"] == "completed"


def test_time_budget_stops_the_loop(repository: MemoryRepository) -> None:
    class SlowProvider(ScriptedProvider):
        def respond(self, **kwargs):
            time.sleep(1.1)
            return super().respond(**kwargs)

    provider = SlowProvider([tool_turn([search_call()])])
    response = make_agent(repository, provider, model_timeout_seconds=1).run(ChatRequest(message="cuti"), ALYA)
    assert len(provider.calls) == 1
    assert response.outcome == "abstained"
    assert repository.get_trace(response.trace_id)["stop_reason"] == "timeout"


# --- LangChain loop (K30): what the framework must not change ---

def test_turn_limit_message_of_langchain_never_reaches_the_user(repository: MemoryRepository) -> None:
    # Balance, not search: without a search no other rule replaces the answer, so only
    # exit_behavior="error" keeps "Model call limits exceeded: run limit (4/4)" away from the user.
    balance = ModelToolCall(call_id="b", name="get_my_leave_balance", arguments={})
    provider = ScriptedProvider([tool_turn([balance])])  # asks for a tool forever
    response = make_agent(repository, provider).run(ChatRequest(message="saldo saya"), ALYA)
    assert response.outcome == "abstained"
    assert "limit" not in response.answer.lower()
    assert repository.get_trace(response.trace_id)["stop_reason"] == "turn_limit"


def test_injected_identity_argument_is_refused_not_dropped(repository: MemoryRepository) -> None:
    """A typed LangChain @tool would silently drop employee_id; our executor must still see and refuse it."""
    injected = ModelToolCall(call_id="x", name="search_hr_policy",
                             arguments={"query": "cuti tahunan", "top_k": 3, "employee_id": "EMP-002"})
    provider = ScriptedProvider([tool_turn([injected]), text_turn("Tidak bisa.")])
    response = make_agent(repository, provider).run(ChatRequest(message="cuti Bima"), ALYA)
    assert [c.status for c in response.tool_calls] == ["blocked"]
    output = next(item["output"] for item in provider.calls[1]["input_data"]
                  if item.get("type") == "function_call_output")
    assert "employee_id" in output


# --- K34: numbers must come from this run's evidence ---

def test_a_wrong_number_behind_a_valid_citation_is_not_shown(repository: MemoryRepository) -> None:
    provider = ScriptedProvider([tool_turn([search_call()]), text_turn("Cuti tahunan 15 hari kerja. [HR-LEAVE-001]")])
    response = make_agent(repository, provider).run(ChatRequest(message="Berapa cuti tahunan?"), ALYA)
    assert response.outcome == "abstained"
    assert "15" not in response.answer
    assert [c.document_id for c in response.citations] == ["HR-LEAVE-001"]  # the real source stays visible
    trace = repository.get_trace(response.trace_id)
    assert trace["stop_reason"] == "unsupported_number"
    assert trace["unsupported_numbers"] == ["15"]


def test_numbers_from_the_document_a_tool_or_the_user_are_accepted(repository: MemoryRepository) -> None:
    balance = ModelToolCall(call_id="b", name="get_my_leave_balance", arguments={})
    provider = ScriptedProvider([
        tool_turn([search_call(), balance]),
        text_turn("Untuk masa kerja 3 tahun jatahnya 12 hari. [HR-LEAVE-001] Saldo tahunan Anda 8 hari."),
    ])
    message = "Saya sudah kerja 3 tahun, berapa jatah cuti tahunan dan saldo saya?"
    response = make_agent(repository, provider).run(ChatRequest(message=message), ALYA)
    assert response.outcome == "answered"  # 12 from the policy, 8 from the balance tool, 3 from the user
    assert repository.get_trace(response.trace_id)["unsupported_numbers"] == []


def test_shadow_mode_only_records_the_unsupported_number(repository: MemoryRepository) -> None:
    provider = ScriptedProvider([tool_turn([search_call()]), text_turn("Cuti tahunan 15 hari kerja. [HR-LEAVE-001]")])
    agent = make_agent(repository, provider, answer_number_check="shadow")
    response = agent.run(ChatRequest(message="Berapa cuti tahunan?"), ALYA)
    assert response.outcome == "answered"
    assert repository.get_trace(response.trace_id)["unsupported_numbers"] == ["15"]


def test_a_tool_name_the_model_made_up_is_refused_and_recorded(repository: MemoryRepository) -> None:
    made_up = ModelToolCall(call_id="m", name="approve_leave", arguments={})
    provider = ScriptedProvider([tool_turn([made_up]), text_turn("Tidak bisa.")])
    response = make_agent(repository, provider).run(ChatRequest(message="setujui cuti saya"), ALYA)
    assert [(c.name, c.status) for c in response.tool_calls] == [("approve_leave", "error")]


# --- Provider contract: stateless conversation, hashed identity ---

def test_provider_receives_strict_tools_hashed_id_and_tool_output(repository: MemoryRepository) -> None:
    provider = ScriptedProvider([tool_turn([search_call("abc")]), text_turn("Hak cuti 12 hari. [HR-LEAVE-001]")])
    make_agent(repository, provider).run(ChatRequest(message="Berapa cuti tahunan?"), ALYA)
    first, second = provider.calls
    assert first["tools"] == TOOL_SCHEMAS
    assert first["safety_identifier"] == stable_safety_id("EMP-001")
    assert "EMP-001" not in first["safety_identifier"]
    assert first["max_output_tokens"] == 700
    # store=False: turn 2 resends the user message, the model's call, and our output for it
    second_items = second["input_data"]
    assert second_items[0] == {"role": "user", "content": "Berapa cuti tahunan?"}
    assert any(i.get("type") == "function_call" and i.get("call_id") == "abc" for i in second_items)
    assert any(i.get("type") == "function_call_output" and i.get("call_id") == "abc" for i in second_items)


# --- Citations ---

def test_section_citation_from_this_run_is_accepted(repository: MemoryRepository) -> None:
    provider = ScriptedProvider([tool_turn([search_call()]), text_turn("12 hari per tahun. [HR-LEAVE-001#hak-dan-saldo]")])
    response = make_agent(repository, provider).run(ChatRequest(message="cuti"), ALYA)
    assert response.outcome == "answered"
    assert response.citations[0].section == "Hak dan saldo"


def test_policy_answer_without_citation_abstains(repository: MemoryRepository) -> None:
    provider = ScriptedProvider([tool_turn([search_call()]), text_turn("Cutinya 20 hari.")])
    response = make_agent(repository, provider).run(ChatRequest(message="cuti"), ALYA)
    assert response.outcome == "abstained"
    assert "20 hari" not in response.answer


def test_citation_of_a_document_not_retrieved_in_this_run_abstains(repository: MemoryRepository) -> None:
    # The model "remembers" a real document ID, but no search happened in this run.
    provider = ScriptedProvider([text_turn("Cuti 12 hari. [HR-LEAVE-001]")])
    response = make_agent(repository, provider).run(ChatRequest(message="cuti"), ALYA)
    assert response.outcome == "abstained" and response.citations == []


# --- End-to-end with the deterministic provider ---

def test_policy_balance_and_proposal_flows(repository: MemoryRepository) -> None:
    agent = make_agent(repository, DeterministicProvider())

    policy = agent.run(ChatRequest(message="Berapa jatah cuti tahunan?"), ALYA)
    assert policy.outcome == "answered" and policy.citations[0].document_id == "HR-LEAVE-001"

    balance = agent.run(ChatRequest(message="Berapa saldo cuti saya?"), ALYA)
    assert balance.outcome == "answered" and "annual 8 hari" in balance.answer

    proposal = agent.run(ChatRequest(message="Siapkan cuti tahunan 2026-09-28 sampai 2026-09-29"), ALYA)
    assert proposal.outcome == "action_proposed"
    assert proposal.action_proposal.business_days == 2
    assert repository.list_leave_requests("EMP-001") == []  # still nothing until Konfirmasi


def test_blocked_leave_request_is_reported_as_abstained(repository: MemoryRepository) -> None:
    """Evaluation case leave-past-009: nothing was done, so the outcome must say so."""
    response = make_agent(repository, DeterministicProvider()).run(
        ChatRequest(message="Ajukan cuti tahunan 2025-01-02"), ALYA
    )
    assert response.outcome == "abstained"
    assert response.action_proposal is None
    assert [(c.name, c.status) for c in response.tool_calls] == [("prepare_leave_request", "blocked")]
    assert "masa lalu" in response.answer  # the reason is still explained to the user


def test_leave_request_the_model_did_not_carry_out_is_abstained(repository: MemoryRepository) -> None:
    """K28, live finding: in 5 of 10 runs the model skipped the tool for a past date and asked
    back or searched policy instead. Nothing was proposed, so the outcome must not be "answered"."""
    asked_back = ScriptedProvider([text_turn("Tanggal itu sudah lewat. Tanggal mulai yang Anda maksud kapan?")])
    response = make_agent(repository, asked_back).run(ChatRequest(message="Ajukan cuti tahunan 2025-01-02"), ALYA)
    assert response.outcome == "abstained" and response.action_proposal is None
    assert "sudah lewat" in response.answer  # the model's explanation still reaches the user
    assert repository.get_trace(response.trace_id)["stop_reason"] == "action_not_performed"


def test_a_question_that_mentions_a_date_is_still_answered(repository: MemoryRepository) -> None:
    provider = ScriptedProvider([text_turn("Tanggal itu hari kerja biasa.")])
    response = make_agent(repository, provider).run(ChatRequest(message="Apakah 2026-12-24 hari kerja?"), ALYA)
    assert response.outcome == "answered"


def test_unknown_policy_abstains(repository: MemoryRepository) -> None:
    response = make_agent(repository, DeterministicProvider()).run(
        ChatRequest(message="Berapa subsidi perjalanan ke Mars?"), ALYA
    )
    assert response.outcome == "abstained"


# --- Output guard and trace privacy ---

def test_output_guard_masks_other_ids_tokens_and_approved(repository: MemoryRepository) -> None:
    provider = ScriptedProvider([text_turn("Saldo EMP-002 tidak bisa dibuka, token-bima rahasia, status approved. Anda EMP-001.")])
    answer = make_agent(repository, provider).run(ChatRequest(message="x"), ALYA).answer
    assert "EMP-002" not in answer and "token-bima" not in answer and "approved" not in answer
    assert "EMP-001" in answer  # the user's own ID is fine


def test_trace_keeps_no_prompt_or_answer(repository: MemoryRepository) -> None:
    message = "Diagnosis saya diabetes, berapa jatah cuti tahunan?"
    response = make_agent(repository, DeterministicProvider()).run(ChatRequest(message=message), ALYA)
    trace = repository.get_trace(response.trace_id)
    dumped = json.dumps(trace)
    assert "message" not in trace and "answer" not in trace
    assert "diabetes" not in dumped and "jatah" not in dumped
    assert trace["employee_id"] == "EMP-001"


def test_a_model_run_never_inserts_a_ticket(repository: MemoryRepository) -> None:
    """K25: even two tool calls in one run only (re)write the draft; nothing reaches the database."""
    ticket = ModelToolCall(call_id="t1", name="create_hr_ticket",
                           arguments={"category": "policy_question", "summary": "Saldo cuti tahunan saya tercatat salah"})
    again = ticket.model_copy(update={"call_id": "t2"})
    provider = ScriptedProvider([tool_turn([ticket, again]), text_turn("Tiket sudah dibuat.")])
    agent = make_agent(repository, provider)
    agent.conversation = ConversationStore(MemoryCache())
    response = agent.run(ChatRequest(message="buat tiket"), ALYA)
    assert [c.status for c in response.tool_calls] == ["ok", "ok"]
    assert repository.tickets == []
    assert response.outcome == "action_proposed"
    assert "BELUM dikirim" in response.answer and "sudah dibuat" not in response.answer
