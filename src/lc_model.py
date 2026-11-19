"""LangChain chat-model adapter around our ModelProvider.

create_agent can only call a LangChain BaseChatModel. Our providers (OpenAI, the deterministic
fake, and the test doubles) speak ModelProvider.respond() -> ModelTurn. This adapter only
translates between the two. Limits, the time budget, and telemetry live in src/lc_agent.py.
"""
from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import ConfigDict

# Where an AIMessage keeps the exact Responses API items the model returned (function calls,
# encrypted reasoning). store=False means we resend them verbatim on the next turn.
OUTPUT_ITEMS = "responses_output_items"


def to_input_items(messages: list[BaseMessage]) -> list[Any]:
    """LangChain messages -> Responses API input items. System messages travel as `instructions`."""
    items: list[Any] = []
    for message in messages:
        if isinstance(message, SystemMessage):
            continue
        if isinstance(message, HumanMessage):
            items.append({"role": "user", "content": message.text})
        elif isinstance(message, AIMessage):
            if OUTPUT_ITEMS in message.additional_kwargs:
                items.extend(message.additional_kwargs[OUTPUT_ITEMS])  # a turn of this run
            else:
                items.append({"role": "assistant", "content": message.text})  # short memory
        elif isinstance(message, ToolMessage):
            items.append({"type": "function_call_output", "call_id": message.tool_call_id,
                          "output": message.text})
        else:
            raise TypeError(f"unsupported message type: {type(message).__name__}")
    return items


class ProviderChatModel(BaseChatModel):
    """A LangChain chat model whose every call is one ModelProvider.respond()."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider: Any  # a ModelProvider; it is a Protocol, so pydantic cannot check the type
    tool_schemas: list[dict[str, Any]]
    max_output_tokens: int

    @property
    def _llm_type(self) -> str:
        return "hr-model-provider"

    def bind_tools(self, tools: list[Any], *, tool_choice: Any = None, **kwargs: Any) -> Any:
        """Offer the model OUR strict schemas for the tools create_agent binds.

        LangChain would build schemas from the tool functions. The hand-written ones in
        src/tools.py stay the source of truth: Responses API strict mode needs every property
        required, nullable types spelled out, and no extra keys.
        """
        names = {tool.name if isinstance(tool, BaseTool) else tool["name"] for tool in tools}
        unknown = names - {schema["name"] for schema in self.tool_schemas}
        if unknown:
            raise ValueError(f"no strict schema for tool(s): {sorted(unknown)}")
        schemas = [schema for schema in self.tool_schemas if schema["name"] in names]
        # kwargs are the request's model_settings (safety_identifier, timeout_seconds, ...);
        # bind() hands them to _generate on every call.
        return self.bind(tools=schemas, **kwargs)

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None,
        run_manager: Any = None, **kwargs: Any,
    ) -> ChatResult:
        turn = self.provider.respond(
            input_data=to_input_items(messages),
            instructions="\n\n".join(m.text for m in messages if isinstance(m, SystemMessage)),
            tools=kwargs.get("tools", []),
            safety_identifier=kwargs["safety_identifier"],  # set per run by RunBudgetMiddleware
            max_output_tokens=self.max_output_tokens,
            timeout_seconds=kwargs.get("timeout_seconds"),
        )
        message = AIMessage(
            content=turn.text,
            tool_calls=[
                {"name": call.name, "args": call.arguments, "id": call.call_id, "type": "tool_call"}
                for call in turn.tool_calls
            ],
            additional_kwargs={OUTPUT_ITEMS: list(turn.output_items)},
            usage_metadata={
                "input_tokens": turn.input_tokens,
                "output_tokens": turn.output_tokens,
                "total_tokens": turn.input_tokens + turn.output_tokens,
            },
            response_metadata={"response_id": turn.response_id},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])
