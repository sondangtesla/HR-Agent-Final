"""Repository contracts. Implement MemoryRepository first, then PostgreSQL/pgvector."""
from __future__ import annotations

import math
from datetime import date
from typing import Any, Protocol

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .contracts import ActionProposal, ActionResult, AuthContext, LeaveBalance, LeaveRequestView, PolicyChunk
from .security import token_hash
from .text import tokenize

CHUNK_COLUMNS = "chunk_id, document_id, title, section, version, effective_date, content"


def to_pgvector(vector: list[float]) -> str:
    # No pgvector Python package (T8): send the '[x,y,...]' text form and cast with ::vector.
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 0.0 if norm == 0 else sum(x * y for x, y in zip(a, b)) / norm


class Repository(Protocol):
    def health(self) -> bool: ...
    def authenticate(self, token: str) -> AuthContext | None: ...
    def lexical_search(self, query: str, limit: int) -> list[PolicyChunk]: ...
    def vector_search(self, embedding: list[float], limit: int) -> list[PolicyChunk]: ...
    def get_balances(self, employee_id: str) -> list[LeaveBalance]: ...
    def has_overlap(self, employee_id: str, start: date, end: date) -> bool: ...
    def save_proposal(self, employee_id: str, proposal: ActionProposal) -> None: ...
    def get_proposal(self, proposal_id: str) -> tuple[str, ActionProposal] | None: ...
    def confirm_proposal(self, employee_id: str, proposal_id: str, idempotency_key: str) -> ActionResult: ...
    def list_leave_requests(self, employee_id: str) -> list[LeaveRequestView]: ...
    def create_ticket(self, employee_id: str, category: str, summary: str) -> str: ...
    def save_trace(self, trace: dict[str, Any]) -> None: ...
    def get_trace(self, trace_id: str) -> dict[str, Any] | None: ...
    def monitoring_summary(self) -> dict[str, Any]: ...


class ConflictError(RuntimeError):
    pass


class MemoryRepository:
    def __init__(self) -> None:
        self.chunks: list[PolicyChunk] = []
        # chunk_id -> vector. Empty by default, so vector_search returns nothing until a test fills it.
        self.embeddings: dict[str, list[float]] = {}
        # TODO(M2): Add isolated in-memory identities, balances, proposals, requests, tickets, and traces.

    def lexical_search(self, query: str, limit: int) -> list[PolicyChunk]:
        """Same idea as the PostgreSQL version: OR over query words, ranked by matches."""
        terms = tokenize(query)
        scored = []
        for chunk in self.chunks:
            words = set(tokenize(f"{chunk.title} {chunk.section} {chunk.content}"))
            matches = sum(term in words for term in terms)
            if matches:
                scored.append((matches, chunk))
        scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return [chunk.model_copy(update={"score": float(m)}) for m, chunk in scored[:limit]]

    def vector_search(self, embedding: list[float], limit: int) -> list[PolicyChunk]:
        scored = [
            (cosine_similarity(embedding, self.embeddings[chunk.chunk_id]), chunk)
            for chunk in self.chunks
            if chunk.chunk_id in self.embeddings
        ]
        scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return [chunk.model_copy(update={"score": s}) for s, chunk in scored[:limit]]

    # TODO(M2): Implement the rest of the Repository protocol for deterministic tests.


class PostgresRepository:
    """PostgreSQL implementation. Every value from outside travels as a %s parameter, never as SQL text."""

    HEALTH_TIMEOUT_SECONDS = 2.0

    def __init__(self, database_url: str, embedding_dimensions: int) -> None:
        self.embedding_dimensions = int(embedding_dimensions)
        # open(wait=False): the API can start while PostgreSQL is still down; health() reports it.
        self.pool = ConnectionPool(
            database_url,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
            open=False,
        )
        self.pool.open(wait=False)

    def close(self) -> None:
        self.pool.close()

    def health(self) -> bool:
        try:
            with self.pool.connection(timeout=self.HEALTH_TIMEOUT_SECONDS) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def authenticate(self, token: str) -> AuthContext | None:
        if not token:
            return None
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT employee_id, display_name, role FROM employees WHERE token_hash = %s",
                (token_hash(token),),
            ).fetchone()
        return AuthContext(**row) if row else None

    def get_balances(self, employee_id: str) -> list[LeaveBalance]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT leave_type, available_days, as_of_date
                FROM leave_balances
                WHERE employee_id = %s
                ORDER BY leave_type
                """,
                (employee_id,),
            ).fetchall()
        return [LeaveBalance(**row) for row in rows]

    def lexical_search(self, query: str, limit: int) -> list[PolicyChunk]:
        """Full-text search with OR between words.

        websearch_to_tsquery joins words with AND, so "jatah cuti tahunan" finds nothing
        because no policy contains "jatah". OR keeps the chunks that match some words,
        and ts_rank puts the ones matching more words first.
        """
        terms = tokenize(query)
        if not terms:
            return []
        # Safe: tokenize() keeps only [a-z0-9], and the string still travels as a parameter.
        tsquery = " | ".join(terms)
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {CHUNK_COLUMNS}, ts_rank(search, q) AS score
                FROM policy_chunks, to_tsquery('simple', %s) AS q
                WHERE search @@ q
                ORDER BY score DESC, chunk_id
                LIMIT %s
                """,
                (tsquery, limit),
            ).fetchall()
        return [PolicyChunk(**row) for row in rows]

    def vector_search(self, embedding: list[float], limit: int) -> list[PolicyChunk]:
        if len(embedding) != self.embedding_dimensions:
            raise ValueError(
                f"query embedding has {len(embedding)} dimensions, expected {self.embedding_dimensions}"
            )
        vector = to_pgvector(embedding)
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {CHUNK_COLUMNS}, 1 - (embedding <=> %s::vector) AS score
                FROM policy_chunks
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector, chunk_id
                LIMIT %s
                """,
                (vector, vector, limit),
            ).fetchall()
        return [PolicyChunk(**row) for row in rows]

    # TODO(M2): Implement transaction-safe persistence for proposals, requests, tickets, and traces.

