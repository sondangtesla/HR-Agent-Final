from __future__ import annotations

import hashlib
import math
from typing import Any, Protocol

from openai import OpenAI

from .config import Settings
from .contracts import ModelTurn
from .text import tokenize


class ModelProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def respond(
        self, *, input_data: str | list[Any], instructions: str,
        tools: list[dict[str, Any]],
        safety_identifier: str, max_output_tokens: int,
    ) -> ModelTurn: ...


class OpenAIProvider:
    """TODO(M2): Implement Responses API function calling and batched embeddings.

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
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
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

    def respond(self, **kwargs: Any) -> ModelTurn:
        # TODO(M2, Step 6): Responses API with store=False, strict tools, hashed safety_identifier.
        raise NotImplementedError


class DeterministicProvider:
    """A network-free fake for tests; never production default."""

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Hashed bag of words: same text, same vector, in every process.

        sha256 instead of hash(): Python's hash() changes per process (see K10).
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

    def respond(self, **kwargs: Any) -> ModelTurn:
        raise NotImplementedError
