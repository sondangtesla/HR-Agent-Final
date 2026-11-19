"""The agent loop, run by LangChain create_agent.

LangChain does the loop: call the model, run the tools it asks for, send the results back, and
repeat until the model answers with text. What stays ours:

- who the user is: AgentRun.auth from the bearer token, passed as `context`, never a tool argument;
- the budget: 4 model calls, 6 tool calls, 30 seconds per run;
- our own argument checks (ToolExecutor), and the per-run telemetry.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool

from .config import Settings
from .contracts import ActionProposal, AuthContext, ToolCallSummary
from .conversation import ConversationStore
from .lc_model import ProviderChatModel
from .providers import ModelProvider
from .tools import TOOL_SCHEMAS, ToolExecutor

# Tools run one at a time, in the order the model asked for them: deterministic telemetry and
# no two side-effect tools racing on the same run. LangGraph would otherwise run them in a thread pool.
RUN_CONFIG = {"max_concurrency": 1}


class DeadlineExceeded(Exception):
    """The run's time budget ran out before the next model call."""


class ProviderFailure(Exception):
    """The model provider failed. The original exception is kept for the redacted trace."""

    def __init__(self, original: Exception) -> None:
        super().__init__(type(original).__name__)
        self.original = original


@dataclass
class AgentRun:
    """One chat run. LangChain passes it to tools and middleware as `context`; the model never sees it."""

    auth: AuthContext
    scope: str
    conversation: ConversationStore | None  # memory and ticket drafts of this scope
    instructions: str
    safety_identifier: str
    deadline: float
    # Recorded while the run goes on.
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    model_ms: int = 0
    tools_ms: int = 0
    tool_calls_requested: int = 0
    tool_summaries: list[ToolCallSummary] = field(default_factory=list)
    retrieved: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    search_rankings: list[list[str]] = field(default_factory=list)  # document IDs per search (recall@k)
    tool_outputs: list[str] = field(default_factory=list)  # what the model saw from tools (number evidence)
    searched: bool = False
    search_failed: bool = False
    action_refused: bool = False
    proposal: ActionProposal | None = None
    ticket_draft: dict[str, str] | None = None

    @property
    def tool_limit_reached(self) -> bool:
        """ToolCallLimitMiddleware answers over-limit calls itself, so they never reach our tools."""
        return self.tool_calls_requested > len(self.tool_summaries)


class ToolRunner:
    """Runs one tool call for the run's user and records it (the body of the old manual loop)."""

    def __init__(self, executor: ToolExecutor) -> None:
        self.executor = executor

    def __call__(self, run: AgentRun, name: str, arguments: dict[str, Any]) -> str:
        started = time.perf_counter()
        result, proposal = self.executor.execute(name, arguments, run.auth)
        if name == "create_hr_ticket" and result["status"] == "ok" and not (
            run.conversation is not None
            and run.conversation.save_draft(run.scope, result["draft"]["category"], result["draft"]["summary"])
        ):
            # Fail closed: a draft that cannot be stored can never be confirmed, so do not show one.
            result = {"status": "blocked", "reason": "Draf tiket tidak dapat disimpan saat ini, jadi "
                      "tiket tidak dibuat. Minta pengguna mencoba lagi nanti."}
        duration = int((time.perf_counter() - started) * 1000)
        run.tools_ms += duration
        run.tool_summaries.append(ToolCallSummary(name=name, status=result["status"], duration_ms=duration))
        if name == "search_hr_policy" and result["status"] == "ok":
            run.searched = True
            run.search_rankings.append([chunk["document_id"] for chunk in result["results"]])
            for chunk in result["results"]:
                run.retrieved.setdefault(chunk["document_id"], []).append(chunk)
        if name == "search_hr_policy" and result["status"] == "error":
            run.search_failed = True
        if name == "create_hr_ticket" and result["status"] == "ok":
            run.ticket_draft = result["draft"]  # a later call replaces the stored draft too
        if name == "prepare_leave_request" and result["status"] != "ok":
            run.action_refused = True
        if proposal is not None:
            run.proposal = proposal
        output = json.dumps(result, ensure_ascii=False)
        run.tool_outputs.append(output)
        return output


def langchain_tools(runner: ToolRunner) -> list[StructuredTool]:
    """One LangChain tool per strict schema.

    args_schema is the JSON-schema dict, so LangChain passes the model's arguments through
    untouched and ToolExecutor still validates them. A typed @tool would silently DROP an
    injected "employee_id" instead of refusing it (checked against langchain-core 1.7.7).
    """
    def make(schema: dict[str, Any]) -> StructuredTool:
        name = schema["name"]

        def call(runtime: ToolRuntime, **arguments: Any) -> str:  # LangChain injects `runtime`
            return runner(runtime.context, name, arguments)

        return StructuredTool.from_function(
            func=call, name=name, description=schema["description"], args_schema=schema["parameters"],
        )

    return [make(schema) for schema in TOOL_SCHEMAS]


class RunBudgetMiddleware(AgentMiddleware):
    """Wraps every model and tool call of a run.

    Model calls: per-run prompt and settings, the time budget, and telemetry. Tool calls: a name
    the model made up goes to our executor (refused and recorded), not to LangChain's own message.
    """

    def __init__(self, runner: ToolRunner) -> None:
        super().__init__()
        self.runner = runner

    def wrap_model_call(self, request, handler):
        run: AgentRun = request.runtime.context
        remaining = run.deadline - time.perf_counter()
        if remaining <= 0:
            raise DeadlineExceeded
        request = request.override(
            system_message=SystemMessage(content=run.instructions),
            model_settings={**request.model_settings, "safety_identifier": run.safety_identifier,
                            "timeout_seconds": remaining},  # never wait longer than the budget left
        )
        started = time.perf_counter()
        try:
            response = handler(request)
        except Exception as exc:  # provider down: stop safely, never retry tools
            raise ProviderFailure(exc) from exc
        finally:
            run.model_ms += int((time.perf_counter() - started) * 1000)
        run.turns += 1
        for message in response.result:
            if isinstance(message, AIMessage):
                usage = message.usage_metadata or {}
                run.input_tokens += usage.get("input_tokens", 0)
                run.output_tokens += usage.get("output_tokens", 0)
                run.tool_calls_requested += len(message.tool_calls)
        return response

    def wrap_tool_call(self, request, handler):
        if request.tool is not None:
            return handler(request)
        call = request.tool_call
        content = self.runner(request.runtime.context, call["name"], call["args"])
        return ToolMessage(content=content, tool_call_id=call["id"], name=call["name"], status="error")


def build_agent(provider: ModelProvider, executor: ToolExecutor, settings: Settings):
    """Compile the agent graph once; every run passes its own AgentRun as `context`."""
    runner = ToolRunner(executor)
    model = ProviderChatModel(
        provider=provider, tool_schemas=TOOL_SCHEMAS, max_output_tokens=settings.max_output_tokens,
    )
    return create_agent(
        model=model,
        tools=langchain_tools(runner),
        context_schema=AgentRun,
        middleware=[
            # "error": stop with an exception we map to turn_limit. The default "end" would add an
            # AIMessage "Model call limits exceeded..." that looks like the model's answer.
            ModelCallLimitMiddleware(run_limit=settings.max_agent_turns, exit_behavior="error"),
            # "continue" (default): calls over the limit get an error message, the model may still answer.
            ToolCallLimitMiddleware(run_limit=settings.max_tool_calls),
            RunBudgetMiddleware(runner),
        ],
    )


def history_messages(history: list[dict[str, str]]) -> list[HumanMessage | AIMessage]:
    """Short memory from Redis as LangChain messages."""
    return [
        HumanMessage(content=item["content"]) if item["role"] == "user" else AIMessage(content=item["content"])
        for item in history
    ]
