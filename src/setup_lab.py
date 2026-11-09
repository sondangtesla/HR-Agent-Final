from __future__ import annotations

from pathlib import Path

import psycopg

from .config import get_settings


ROOT = Path(__file__).resolve().parents[1]

LEAVE_TYPES = "('annual', 'sick', 'parental')"

# {dimensions} is the only placeholder. It comes from Settings (an int validated
# to 64..4096), never from user input, and is cast with int() before formatting.
SCHEMA_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS employees (
    employee_id   TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('employee', 'monitoring_admin')),
    token_hash    TEXT NOT NULL UNIQUE CHECK (char_length(token_hash) = 64)
);

CREATE TABLE IF NOT EXISTS leave_balances (
    employee_id     TEXT NOT NULL REFERENCES employees (employee_id),
    leave_type      TEXT NOT NULL CHECK (leave_type IN {LEAVE_TYPES}),
    available_days  INTEGER NOT NULL CHECK (available_days >= 0),
    as_of_date      DATE NOT NULL,
    PRIMARY KEY (employee_id, leave_type)
);

CREATE TABLE IF NOT EXISTS action_proposals (
    proposal_id         TEXT PRIMARY KEY,
    employee_id         TEXT NOT NULL REFERENCES employees (employee_id),
    action_type         TEXT NOT NULL DEFAULT 'leave_request'
                        CHECK (action_type = 'leave_request'),
    leave_type          TEXT NOT NULL CHECK (leave_type IN {LEAVE_TYPES}),
    start_date          DATE NOT NULL,
    end_date            DATE NOT NULL,
    business_days       INTEGER NOT NULL CHECK (business_days > 0),
    reason              TEXT,
    validation_summary  JSONB NOT NULL DEFAULT '[]'::jsonb,
    policy_version      TEXT NOT NULL,
    expires_at          TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (end_date >= start_date)
);

-- K9: the assistant may only ever set pending_manager_review.
-- approved/cancelled are allowed only when written by the HR system or the seed.
CREATE TABLE IF NOT EXISTS leave_requests (
    request_id       TEXT PRIMARY KEY,
    employee_id      TEXT NOT NULL REFERENCES employees (employee_id),
    leave_type       TEXT NOT NULL CHECK (leave_type IN {LEAVE_TYPES}),
    start_date       DATE NOT NULL,
    end_date         DATE NOT NULL,
    business_days    INTEGER NOT NULL CHECK (business_days > 0),
    status           TEXT NOT NULL
                     CHECK (status IN ('pending_manager_review', 'approved', 'cancelled')),
    status_set_by    TEXT NOT NULL CHECK (status_set_by IN ('assistant', 'hr_system', 'seed')),
    proposal_id      TEXT UNIQUE REFERENCES action_proposals (proposal_id),
    idempotency_key  TEXT,
    policy_version   TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (end_date >= start_date),
    CONSTRAINT assistant_writes_only_pending
        CHECK (status_set_by <> 'assistant' OR status = 'pending_manager_review'),
    CONSTRAINT assistant_request_has_proposal_key_and_policy CHECK (
        status_set_by <> 'assistant'
        OR (proposal_id IS NOT NULL AND idempotency_key IS NOT NULL AND policy_version IS NOT NULL)
    ),
    UNIQUE (employee_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS leave_requests_employee_status_idx
    ON leave_requests (employee_id, status);

CREATE TABLE IF NOT EXISTS hr_tickets (
    ticket_id    TEXT PRIMARY KEY,
    employee_id  TEXT NOT NULL REFERENCES employees (employee_id),
    category     TEXT NOT NULL
                 CHECK (category IN ('policy_question', 'leave_exception', 'technical_issue', 'privacy')),
    summary      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS policy_chunks (
    chunk_id        TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL,
    title           TEXT NOT NULL,
    section         TEXT NOT NULL,
    version         TEXT NOT NULL,
    effective_date  DATE NOT NULL,
    content         TEXT NOT NULL,
    embedding       vector({{dimensions}}),
    search          tsvector GENERATED ALWAYS AS (
                        to_tsvector('simple', title || ' ' || section || ' ' || content)
                    ) STORED
);

CREATE INDEX IF NOT EXISTS policy_chunks_search_idx
    ON policy_chunks USING GIN (search);

CREATE TABLE IF NOT EXISTS traces (
    trace_id     TEXT PRIMARY KEY,
    employee_id  TEXT NOT NULL REFERENCES employees (employee_id),
    payload      JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS traces_created_at_idx ON traces (created_at);
"""


def create_schema(conn: psycopg.Connection, embedding_dimensions: int) -> None:
    """Create every table if it does not exist yet. Safe to run more than once."""
    dimensions = int(embedding_dimensions)
    if not 64 <= dimensions <= 4096:
        raise ValueError("embedding_dimensions must be between 64 and 4096")
    conn.execute(SCHEMA_SQL.format(dimensions=dimensions))


def chunk_policy(path: Path) -> list[dict[str, str]]:
    # TODO(M2): Parse front matter and deterministic section chunks with stable IDs.
    raise NotImplementedError


def reset_and_seed() -> None:
    settings = get_settings()
    with psycopg.connect(settings.database_url) as conn:
        create_schema(conn, settings.embedding_dimensions)
    print("Schema siap.")
    # TODO(M2): --reset, seed synthetic identities/balances, batch embed, and upsert chunks.


if __name__ == "__main__":
    reset_and_seed()
