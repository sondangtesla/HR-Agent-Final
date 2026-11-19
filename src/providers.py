from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Protocol

from openai import OpenAI

from .config import Settings
from .contracts import ModelToolCall, ModelTurn
from .text import tokenize


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


class ModelProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def respond(
        self, *, input_data: str | list[Any], instructions: str,
        tools: list[dict[str, Any]],
        safety_identifier: str, max_output_tokens: int,
        timeout_seconds: float | None = None,
    ) -> ModelTurn: ...


class OpenAIProvider:
    """OpenAI Responses API: function calling and batched embeddings.

    Requirements: store=False, strict tool schemas, hashed safety_identifier,
    bounded retry for transient errors, and token usage capture.
    """

    EMBED_BATCH_SIZE = 64

    def __init__(
        self,
        *,
        api_key: str,
        agent_model: str,
        embedding_model: str,
        embedding_dimensions: int,
        timeout_seconds: float,
        base_url: str | None = None,
        max_retries: int = 2,
    ) -> None:
        if not api_key or not embedding_model:
            raise ValueError("OPENAI_API_KEY and EMBEDDING_MODEL are required for OpenAIProvider")
        self.agent_model = agent_model
        self.embedding_model = embedding_model
        self.embedding_dimensions = int(embedding_dimensions)
        # The SDK retries transient failures (connection errors, 408, 409, 429, 5xx) with backoff.
        # max_retries makes that retry bounded; timeout bounds every single attempt.
        # base_url is never left to the SDK: with base_url=None it reads OPENAI_BASE_URL from the
        # environment, and Compose always sets it, to "" when unset. The SDK then sends every
        # request to "" (found in the clean-checkout Docker run, 10 Nov 2026).
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url or DEFAULT_OPENAI_BASE_URL,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIProvider":
        return cls(
            api_key=settings.openai_api_key or "",
            agent_model=settings.agent_model,
            embedding_model=settings.embedding_model,
            embedding_dimensions=settings.embedding_dimensions,
            timeout_seconds=settings.model_timeout_seconds,
            base_url=settings.openai_base_url,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in batches. Every vector is checked before anyone can store it."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.EMBED_BATCH_SIZE):
            batch = texts[start : start + self.EMBED_BATCH_SIZE]
            response = self.client.embeddings.create(model=self.embedding_model, input=batch)
            items = sorted(response.data, key=lambda item: item.index)
            if len(items) != len(batch):
                raise ValueError(f"expected {len(batch)} embeddings, got {len(items)}")
            for item in items:
                if len(item.embedding) != self.embedding_dimensions:
                    raise ValueError(
                        f"embedding has {len(item.embedding)} dimensions, "
                        f"EMBEDDING_DIMENSIONS is {self.embedding_dimensions}"
                    )
                vectors.append(list(item.embedding))
        return vectors

    def respond(
        self, *, input_data: str | list[Any], instructions: str,
        tools: list[dict[str, Any]],
        safety_identifier: str, max_output_tokens: int,
        timeout_seconds: float | None = None,
    ) -> ModelTurn:
        """One model turn.

        store=False: OpenAI keeps no conversation, so the agent resends every item each turn
        (ModelTurn.output_items). Encrypted reasoning items are requested so reasoning models
        can continue without server-side state; their content is never readable or stored by us.
        Transient failures are retried by the SDK (max_retries), never by re-running tools.
        """
        client = self.client
        if timeout_seconds is not None:
            # The agent's 30 s budget is shared by all turns: never wait longer than what is left.
            client = client.with_options(timeout=max(1.0, timeout_seconds))
        response = client.responses.create(
            model=self.agent_model,
            instructions=instructions,
            input=input_data,
            tools=tools,
            store=False,
            include=["reasoning.encrypted_content"],
            max_output_tokens=max_output_tokens,
            safety_identifier=safety_identifier,
        )
        tool_calls: list[ModelToolCall] = []
        output_items: list[Any] = []
        for item in response.output:
            output_items.append(item.model_dump(mode="json", exclude_none=True))
            if item.type == "function_call":
                try:
                    arguments = json.loads(item.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {"_invalid_json": True}  # the executor refuses unknown keys
                if not isinstance(arguments, dict):
                    arguments = {"_invalid_json": True}
                tool_calls.append(ModelToolCall(call_id=item.call_id, name=item.name, arguments=arguments))
        usage = response.usage
        return ModelTurn(
            response_id=response.id,
            text=response.output_text or "",
            tool_calls=tool_calls,
            output_items=output_items,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
        )


class UnavailableProvider:
    """Stands in when live mode has no API key or model. Every call fails, so retrieval falls
    back to lexical search, the agent abstains safely, and /readyz reports not ready."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("model provider is not configured")

    def respond(self, **kwargs: Any) -> ModelTurn:
        raise RuntimeError("model provider is not configured")


class DeterministicProvider:
    """A network-free fake for tests; never production default."""

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Hashed bag of words: same text, same vector, in every process.

        sha256 instead of hash(): Python's hash() changes per process.
        """
        vectors = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in tokenize(text):
                index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % self.dimensions
                vector[index] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors

    def respond(self, *, input_data: str | list[Any], **kwargs: Any) -> ModelTurn:
        """Scripted two-step behaviour: first pick one tool from keywords, then answer from its output.

        It reads the same item format the real Responses API uses, so the agent loop is
        exercised exactly as in production, without network.
        """
        items = [input_data] if isinstance(input_data, str) else list(input_data)
        outputs = [item for item in items if isinstance(item, dict) and item.get("type") == "function_call_output"]
        if not outputs:
            # The LAST user message: short memory puts earlier messages before it.
            message = next(
                (item["content"] for item in reversed(items) if isinstance(item, dict) and item.get("role") == "user"),
                items[0] if items and isinstance(items[0], str) else "",
            )
            name, arguments = self._choose_tool(message)
            call = {
                "type": "function_call",
                "call_id": f"call-{name}",
                "name": name,
                "arguments": json.dumps(arguments),
            }
            return ModelTurn(
                response_id="fake-1",
                tool_calls=[ModelToolCall(call_id=call["call_id"], name=name, arguments=arguments)],
                output_items=[call],
                input_tokens=len(message.split()),
            )
        result = json.loads(outputs[-1]["output"])
        text = self._answer(result)
        return ModelTurn(
            response_id="fake-2",
            text=text,
            output_items=[{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}],
            output_tokens=len(text.split()),
        )

    @staticmethod
    def _choose_tool(message: str) -> tuple[str, dict[str, Any]]:
        lower = message.lower()
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", message)
        if dates and "cuti" in lower:
            leave_type = "sick" if "sakit" in lower else "parental" if "orang tua" in lower else "annual"
            return "prepare_leave_request", {
                "start_date": dates[0], "end_date": dates[-1], "leave_type": leave_type, "reason": None,
            }
        if "tiket" in lower:
            category = "privacy" if "privasi" in lower else "leave_exception" if "pengecualian" in lower else "policy_question"
            return "create_hr_ticket", {"category": category, "summary": message[:500]}
        if "saldo" in lower:
            return "get_my_leave_balance", {}
        return "search_hr_policy", {"query": message, "top_k": 3}

    @staticmethod
    def _answer(result: dict[str, Any]) -> str:
        if result.get("status") != "ok":
            return f"Permintaan tidak dapat diproses: {result.get('reason', 'alasan tidak diketahui')}"
        if "results" in result:
            if not result["results"]:
                return "Saya tidak menemukan kebijakan yang relevan untuk pertanyaan ini."
            top = result["results"][0]
            return f"Menurut {top['title']} bagian {top['section']}: {top['excerpt']} [{top['document_id']}]"
        if "balances" in result:
            parts = [
                f"{b['leave_type']} {b['balance_days']} hari (bisa diajukan {b['available_to_request_days']})"
                for b in result["balances"]
            ]
            return "Saldo cuti Anda: " + ", ".join(parts) + "."
        if "proposal_id" in result:
            return f"{result['message']} Total {result['business_days']} hari kerja."
        if "draft" in result:
            return "Draf tiket sudah disiapkan dan menunggu konfirmasi Anda."
        return "Selesai."
