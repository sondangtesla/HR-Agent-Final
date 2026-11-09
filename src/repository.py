"""Repository contracts. Implement MemoryRepository first, then PostgreSQL/pgvector."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .contracts import ActionProposal, ActionResult, AuthContext, LeaveBalance, LeaveRequestView, PolicyChunk
from .domain import ACTIVE_STATUSES, RULE_POLICY_VERSIONS, today_wib
from .monitoring import summarize
from .security import redact, token_hash
from .text import tokenize

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CHUNK_COLUMNS = "chunk_id, document_id, title, section, version, effective_date, content"
REQUEST_COLUMNS = "request_id, leave_type, start_date, end_date, business_days, status, created_at"
PROPOSAL_COLUMNS = (
    "proposal_id, action_type, leave_type, start_date, end_date, business_days, "
    "reason, validation_summary, expires_at"
)


def new_ticket_id() -> str:
    return "HRT-" + uuid.uuid4().hex[:12].upper()


def new_request_id() -> str:
    return "LR-" + uuid.uuid4().hex[:12].upper()


def audit_reference(request_id: str) -> str:
    """Derived from the request ID, so an idempotent replay returns the same reference."""
    return "AUD-" + hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:12].upper()


EXPIRED_MESSAGE = "Proposal sudah kedaluwarsa (expired). Siapkan proposal baru."
ALREADY_CONFIRMED_MESSAGE = "Proposal ini sudah dikonfirmasi dengan idempotency key lain."
KEY_REUSED_MESSAGE = "Idempotency key ini sudah dipakai untuk proposal lain."


def insufficient_balance_message(leave_type: str, requested: int, available: int) -> str:
    return (
        f"Saldo cuti {leave_type} tidak cukup lagi saat konfirmasi: diminta {requested} hari, "
        f"tersedia {available} hari setelah dikurangi permintaan yang masih menunggu manajer."
    )


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
    def get_pending_days(self, employee_id: str) -> dict[str, int]: ...
    def has_overlap(self, employee_id: str, start: date, end: date) -> bool: ...
    def save_proposal(self, employee_id: str, proposal: ActionProposal) -> None: ...
    def get_proposal(self, proposal_id: str) -> tuple[str, ActionProposal] | None: ...
    def confirm_proposal(self, employee_id: str, proposal_id: str, idempotency_key: str) -> ActionResult: ...
    def list_leave_requests(self, employee_id: str) -> list[LeaveRequestView]: ...
    def create_ticket(self, employee_id: str, category: str, summary: str) -> str: ...
    def save_trace(self, trace: dict[str, Any]) -> None: ...
    def get_trace(self, trace_id: str) -> dict[str, Any] | None: ...
    def monitoring_summary(self) -> dict[str, Any]: ...
    def index_status(self) -> dict[str, int]: ...


class ConflictError(RuntimeError):
    pass


class MemoryRepository:
    """Deterministic in-memory repository for tests. Every instance is isolated.

    It loads the synthetic identities and balances from data/employees.json, so demo tokens
    work, but NOT the historical requests: tests expect an employee to start with no requests.
    """

    def __init__(self) -> None:
        self.chunks: list[PolicyChunk] = []
        # chunk_id -> vector. Empty by default, so vector_search returns nothing until a test fills it.
        self.embeddings: dict[str, list[float]] = {}
        self.identities: dict[str, AuthContext] = {}  # token_hash -> identity
        self.balances: dict[str, list[LeaveBalance]] = {}
        self.proposals: dict[str, tuple[str, ActionProposal]] = {}
        # (employee_id, request). Tests may append rows directly to set up a scenario.
        self.requests: list[tuple[str, LeaveRequestView]] = []
        self.tickets: list[dict[str, Any]] = []
        self.traces: dict[str, dict[str, Any]] = {}
        # Mirrors UNIQUE(proposal_id) and UNIQUE(employee_id, idempotency_key) from the schema (K9).
        self.confirmations: dict[str, tuple[str, str]] = {}  # proposal_id -> (request_id, key)
        self.keys: dict[tuple[str, str], str] = {}  # (employee_id, key) -> proposal_id
        self._lock = threading.Lock()  # stands in for the PostgreSQL row/advisory locks

        as_of = today_wib()
        for row in json.loads((DATA_DIR / "employees.json").read_text(encoding="utf-8")):
            identity = AuthContext.model_validate(row)
            self.identities[token_hash(row["token"])] = identity
            self.balances[identity.employee_id] = [
                LeaveBalance(leave_type=leave_type, available_days=days, as_of_date=as_of)
                for leave_type, days in row.get("balances", {}).items()
            ]

    def health(self) -> bool:
        return True

    def authenticate(self, token: str) -> AuthContext | None:
        return self.identities.get(token_hash(token)) if token else None

    def get_balances(self, employee_id: str) -> list[LeaveBalance]:
        return sorted(self.balances.get(employee_id, []), key=lambda b: b.leave_type)

    def get_pending_days(self, employee_id: str) -> dict[str, int]:
        totals: dict[str, int] = {}
        for owner, request in self.requests:
            if owner == employee_id and request.status == "pending_manager_review":
                totals[request.leave_type] = totals.get(request.leave_type, 0) + request.business_days
        return totals

    def has_overlap(self, employee_id: str, start: date, end: date) -> bool:
        return any(
            owner == employee_id
            and request.status in ACTIVE_STATUSES
            and request.start_date <= end
            and request.end_date >= start
            for owner, request in self.requests
        )

    def save_proposal(self, employee_id: str, proposal: ActionProposal) -> None:
        self.proposals[proposal.proposal_id] = (employee_id, proposal)

    def get_proposal(self, proposal_id: str) -> tuple[str, ActionProposal] | None:
        return self.proposals.get(proposal_id)

    def list_leave_requests(self, employee_id: str) -> list[LeaveRequestView]:
        mine = [request for owner, request in self.requests if owner == employee_id]
        return sorted(mine, key=lambda r: (r.created_at, r.request_id), reverse=True)

    def create_ticket(self, employee_id: str, category: str, summary: str) -> str:
        ticket_id = new_ticket_id()
        self.tickets.append(
            {"ticket_id": ticket_id, "employee_id": employee_id, "category": category, "summary": redact(summary)}
        )
        return ticket_id

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

    def save_trace(self, trace: dict[str, Any]) -> None:
        # Stored as JSON text and read back as a new dict: callers can never mutate stored traces.
        self.traces[trace["trace_id"]] = json.loads(json.dumps(trace))

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        stored = self.traces.get(trace_id)
        return json.loads(json.dumps(stored)) if stored else None

    def monitoring_summary(self) -> dict[str, Any]:
        return summarize(list(self.traces.values()))

    def index_status(self) -> dict[str, int]:
        # Memory tests run lexical-only, so missing vectors do not make the index "not ready".
        return {"chunks": len(self.chunks), "missing_embeddings": 0}

    def confirm_proposal(self, employee_id: str, proposal_id: str, idempotency_key: str) -> ActionResult:
        """Same rules and order as PostgresRepository.confirm_proposal."""
        with self._lock:
            stored = self.proposals.get(proposal_id)
            if stored is None or stored[0] != employee_id:
                raise KeyError(proposal_id)
            proposal = stored[1]

            if proposal_id in self.confirmations:
                request_id, key = self.confirmations[proposal_id]
                if key == idempotency_key:
                    return ActionResult(request_id=request_id, idempotent_replay=True,
                                        audit_reference=audit_reference(request_id))
                raise ConflictError(ALREADY_CONFIRMED_MESSAGE)
            if (employee_id, idempotency_key) in self.keys:
                raise ConflictError(KEY_REUSED_MESSAGE)
            if proposal.expires_at <= datetime.now(timezone.utc):
                raise ConflictError(EXPIRED_MESSAGE)
            if self.has_overlap(employee_id, proposal.start_date, proposal.end_date):
                raise ConflictError("Tanggal bertumpang tindih dengan permintaan cuti yang masih aktif.")
            balance = next((b.available_days for b in self.balances.get(employee_id, [])
                            if b.leave_type == proposal.leave_type), 0)
            available = balance - self.get_pending_days(employee_id).get(proposal.leave_type, 0)
            if proposal.business_days > available:
                raise ConflictError(insufficient_balance_message(proposal.leave_type, proposal.business_days, max(0, available)))

            request_id = new_request_id()
            self.requests.append((employee_id, LeaveRequestView(
                request_id=request_id, leave_type=proposal.leave_type,
                start_date=proposal.start_date, end_date=proposal.end_date,
                business_days=proposal.business_days, status="pending_manager_review",
                created_at=datetime.now(timezone.utc),
            )))
            self.confirmations[proposal_id] = (request_id, idempotency_key)
            self.keys[(employee_id, idempotency_key)] = proposal_id
            return ActionResult(request_id=request_id, idempotent_replay=False,
                                audit_reference=audit_reference(request_id))


class PostgresRepository:
    """PostgreSQL implementation. Every value from outside travels as a %s parameter, never as SQL text."""

    HEALTH_TIMEOUT_SECONDS = 2.0
    # A request waits at most this long for a connection, then fails fast (API answers 503).
    REQUEST_TIMEOUT_SECONDS = 5.0

    def __init__(self, database_url: str, embedding_dimensions: int) -> None:
        self.database_url = database_url
        self.embedding_dimensions = int(embedding_dimensions)
        self.pool = self._new_pool()

    def _new_pool(self) -> ConnectionPool:
        # open(wait=False): the API can start while PostgreSQL is still down; health() reports it.
        # check_connection: a connection that died while idle is replaced before a request gets it.
        pool = ConnectionPool(
            self.database_url,
            min_size=1,
            max_size=5,
            timeout=self.REQUEST_TIMEOUT_SECONDS,
            check=ConnectionPool.check_connection,
            kwargs={"row_factory": dict_row},
            open=False,
        )
        pool.open(wait=False)
        return pool

    def close(self) -> None:
        self.pool.close()

    def health(self) -> bool:
        """True when PostgreSQL answers. Also heals a stale pool.

        After an outage the pool retries with exponential backoff (1, 2, 4, ... s), so it can
        stay broken for a minute after PostgreSQL is back. If the pool fails but a direct
        connection works, the database is fine and the pool is replaced.
        """
        try:
            with self.pool.connection(timeout=self.HEALTH_TIMEOUT_SECONDS) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            pass
        try:
            with psycopg.connect(self.database_url, connect_timeout=int(self.HEALTH_TIMEOUT_SECONDS)) as conn:
                conn.execute("SELECT 1")
        except Exception:
            return False
        stale, self.pool = self.pool, self._new_pool()
        logger.warning("database reachable but pool was stale; pool replaced")
        stale.close(timeout=1.0)
        return True

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

    @staticmethod
    def _pending_days(conn: psycopg.Connection, employee_id: str) -> dict[str, int]:
        rows = conn.execute(
            """
            SELECT leave_type, sum(business_days)::int AS days
            FROM leave_requests
            WHERE employee_id = %s AND status = 'pending_manager_review'
            GROUP BY leave_type
            """,
            (employee_id,),
        ).fetchall()
        return {row["leave_type"]: row["days"] for row in rows}

    @staticmethod
    def _overlaps(conn: psycopg.Connection, employee_id: str, start: date, end: date) -> bool:
        row = conn.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM leave_requests
                WHERE employee_id = %s
                  AND status = ANY(%s)
                  AND start_date <= %s
                  AND end_date >= %s
            ) AS overlaps
            """,
            (employee_id, sorted(ACTIVE_STATUSES), end, start),
        ).fetchone()
        return bool(row["overlaps"])

    def get_pending_days(self, employee_id: str) -> dict[str, int]:
        with self.pool.connection() as conn:
            return self._pending_days(conn, employee_id)

    def has_overlap(self, employee_id: str, start: date, end: date) -> bool:
        with self.pool.connection() as conn:
            return self._overlaps(conn, employee_id, start, end)

    def save_proposal(self, employee_id: str, proposal: ActionProposal) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO action_proposals (
                    proposal_id, employee_id, action_type, leave_type, start_date, end_date,
                    business_days, reason, validation_summary, policy_version, expires_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    proposal.proposal_id,
                    employee_id,
                    proposal.action_type,
                    proposal.leave_type,
                    proposal.start_date,
                    proposal.end_date,
                    proposal.business_days,
                    proposal.reason,
                    Jsonb(proposal.validation_summary),
                    RULE_POLICY_VERSIONS[proposal.leave_type],
                    proposal.expires_at,
                ),
            )

    def get_proposal(self, proposal_id: str) -> tuple[str, ActionProposal] | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                f"SELECT employee_id, {PROPOSAL_COLUMNS} FROM action_proposals WHERE proposal_id = %s",
                (proposal_id,),
            ).fetchone()
        if row is None:
            return None
        employee_id = row.pop("employee_id")
        return employee_id, ActionProposal(**row)

    def list_leave_requests(self, employee_id: str) -> list[LeaveRequestView]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {REQUEST_COLUMNS}
                FROM leave_requests
                WHERE employee_id = %s
                ORDER BY created_at DESC, request_id DESC
                """,
                (employee_id,),
            ).fetchall()
        return [LeaveRequestView(**row) for row in rows]

    def confirm_proposal(self, employee_id: str, proposal_id: str, idempotency_key: str) -> ActionResult:
        """Turn a proposal into exactly one pending request, in one transaction.

        Order (each step can end the call):
          1. per-employee advisory lock: two different proposals of the same employee cannot
             pass the balance check at the same time (K8)
          2. row lock on the proposal; unknown or someone else's -> KeyError (API: 404)
          3. already confirmed: same key -> replay of the same request; other key -> conflict
          4. key already used for another proposal -> conflict
          5. expired -> conflict. Checked AFTER idempotency, so a retry of a confirm that
             succeeded still gets its answer even if the proposal expired since.
          6. overlap and effective balance checked again: other requests may exist by now
          7. insert pending_manager_review (status_set_by='assistant'), mark proposal confirmed
        """
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (employee_id,))
            proposal = conn.execute(
                """
                SELECT employee_id, leave_type, start_date, end_date, business_days,
                       policy_version, expires_at
                FROM action_proposals WHERE proposal_id = %s
                FOR UPDATE
                """,
                (proposal_id,),
            ).fetchone()
            if proposal is None or proposal["employee_id"] != employee_id:
                raise KeyError(proposal_id)

            existing = conn.execute(
                "SELECT request_id, idempotency_key FROM leave_requests WHERE proposal_id = %s",
                (proposal_id,),
            ).fetchone()
            if existing:
                if existing["idempotency_key"] == idempotency_key:
                    return ActionResult(request_id=existing["request_id"], idempotent_replay=True,
                                        audit_reference=audit_reference(existing["request_id"]))
                raise ConflictError(ALREADY_CONFIRMED_MESSAGE)
            key_used = conn.execute(
                "SELECT 1 FROM leave_requests WHERE employee_id = %s AND idempotency_key = %s",
                (employee_id, idempotency_key),
            ).fetchone()
            if key_used:
                raise ConflictError(KEY_REUSED_MESSAGE)
            if proposal["expires_at"] <= datetime.now(timezone.utc):
                raise ConflictError(EXPIRED_MESSAGE)

            if self._overlaps(conn, employee_id, proposal["start_date"], proposal["end_date"]):
                raise ConflictError("Tanggal bertumpang tindih dengan permintaan cuti yang masih aktif.")
            balance_row = conn.execute(
                "SELECT available_days FROM leave_balances WHERE employee_id = %s AND leave_type = %s",
                (employee_id, proposal["leave_type"]),
            ).fetchone()
            balance = balance_row["available_days"] if balance_row else 0
            available = balance - self._pending_days(conn, employee_id).get(proposal["leave_type"], 0)
            if proposal["business_days"] > available:
                raise ConflictError(insufficient_balance_message(
                    proposal["leave_type"], proposal["business_days"], max(0, available)))

            request_id = new_request_id()
            conn.execute(
                """
                INSERT INTO leave_requests (
                    request_id, employee_id, leave_type, start_date, end_date, business_days,
                    status, status_set_by, proposal_id, idempotency_key, policy_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'pending_manager_review', 'assistant', %s, %s, %s)
                """,
                (request_id, employee_id, proposal["leave_type"], proposal["start_date"],
                 proposal["end_date"], proposal["business_days"], proposal_id, idempotency_key,
                 proposal["policy_version"]),
            )
            conn.execute("UPDATE action_proposals SET confirmed_at = now() WHERE proposal_id = %s", (proposal_id,))
        return ActionResult(request_id=request_id, idempotent_replay=False,
                            audit_reference=audit_reference(request_id))

    def create_ticket(self, employee_id: str, category: str, summary: str) -> str:
        """The summary is redacted here, at the storage boundary, whatever the caller did."""
        ticket_id = new_ticket_id()
        with self.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO hr_tickets (ticket_id, employee_id, category, summary)
                VALUES (%s, %s, %s, %s)
                """,
                (ticket_id, employee_id, category, redact(summary)),
            )
        return ticket_id

    def save_trace(self, trace: dict[str, Any]) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO traces (trace_id, employee_id, payload) VALUES (%s, %s, %s)",
                (trace["trace_id"], trace["employee_id"], Jsonb(trace)),
            )

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT payload FROM traces WHERE trace_id = %s", (trace_id,)).fetchone()
        return row["payload"] if row else None

    MONITORING_WINDOW_HOURS = 24

    def monitoring_summary(self) -> dict[str, Any]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT payload FROM traces WHERE created_at >= now() - make_interval(hours => %s)",
                (self.MONITORING_WINDOW_HOURS,),
            ).fetchall()
        summary = summarize([row["payload"] for row in rows])
        summary["window_hours"] = self.MONITORING_WINDOW_HOURS
        return summary

    def index_status(self) -> dict[str, int]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT count(*) AS chunks,
                       count(*) FILTER (WHERE embedding IS NULL) AS missing_embeddings
                FROM policy_chunks
                """
            ).fetchone()
        return {"chunks": row["chunks"], "missing_embeddings": row["missing_embeddings"]}


