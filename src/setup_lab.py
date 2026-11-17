from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from .config import get_settings
from .contracts import AuthContext, LeaveBalance, LeaveRequestView, PolicyChunk
from .domain import today_wib
from .providers import ModelProvider, OpenAIProvider
from .repository import to_pgvector
from .security import token_hash


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

# Fixed identifiers (never user input). One DROP statement handles the foreign keys between them.
TABLES = (
    "leave_requests",
    "action_proposals",
    "leave_balances",
    "hr_tickets",
    "traces",
    "policy_chunks",
    "employees",
)

LEAVE_TYPES = "('annual', 'sick', 'parental')"

# {dimensions} is the only placeholder. It comes from Settings (an int validated
# to 64..4096), never from user input, and is cast with int() before formatting.
SCHEMA_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS employees (
    employee_id   TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('employee', 'monitoring_admin', 'manager')),
    token_hash    TEXT NOT NULL UNIQUE CHECK (char_length(token_hash) = 64),
    department    TEXT,
    manager_id    TEXT REFERENCES employees (employee_id)
);
-- CREATE TABLE IF NOT EXISTS tidak mengubah tabel yang sudah ada, jadi kolom dan role baru
-- juga ditambahkan lewat ALTER. Kolom baru selalu di akhir: ada test yang INSERT tanpa nama kolom.
ALTER TABLE employees ADD COLUMN IF NOT EXISTS department TEXT;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS manager_id TEXT REFERENCES employees (employee_id);
ALTER TABLE employees DROP CONSTRAINT IF EXISTS employees_role_check;
ALTER TABLE employees ADD CONSTRAINT employees_role_check
    CHECK (role IN ('employee', 'monitoring_admin', 'manager'));

CREATE TABLE IF NOT EXISTS leave_balances (
    employee_id     TEXT NOT NULL REFERENCES employees (employee_id),
    leave_type      TEXT NOT NULL CHECK (leave_type IN {LEAVE_TYPES}),
    available_days  INTEGER NOT NULL CHECK (available_days >= 0),
    as_of_date      DATE NOT NULL,
    updated_at      TIMESTAMPTZ,
    PRIMARY KEY (employee_id, leave_type)
);
-- T6: CREATE TABLE IF NOT EXISTS does not change an existing table.
ALTER TABLE leave_balances ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

-- K26: only the table owner (the HR system / seed) may RAISE a balance. Every other login,
-- including hr_api, can only lower it, so even a bug in the API cannot give anyone more leave.
-- updated_at is set here, not by the application, as the audit trail of every change.
CREATE OR REPLACE FUNCTION guard_balance_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.available_days > OLD.available_days
       AND current_user <> (SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = TG_RELID) THEN
        RAISE EXCEPTION 'saldo cuti hanya boleh dikurangi oleh login ini'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS leave_balances_guard ON leave_balances;
CREATE TRIGGER leave_balances_guard BEFORE UPDATE ON leave_balances
    FOR EACH ROW EXECUTE FUNCTION guard_balance_update();

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
    confirmed_at        TIMESTAMPTZ,
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
    status          TEXT NOT NULL DEFAULT 'berlaku' CHECK (status IN ('berlaku', 'arsip')),
    embedding       vector({{dimensions}}),
    search          tsvector GENERATED ALWAYS AS (
                        to_tsvector('simple', title || ' ' || section || ' ' || content)
                    ) STORED
);

-- K32: databases created before the status column get it here; the next seed sets the real value.
ALTER TABLE policy_chunks
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'berlaku' CHECK (status IN ('berlaku', 'arsip'));

CREATE INDEX IF NOT EXISTS policy_chunks_search_idx
    ON policy_chunks USING GIN (search);

CREATE TABLE IF NOT EXISTS traces (
    trace_id     TEXT PRIMARY KEY,
    employee_id  TEXT NOT NULL REFERENCES employees (employee_id),
    payload      JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS traces_created_at_idx ON traces (created_at);

-- K26: the days taken at confirmation go back when the HR system cancels the request.
-- Only requests made through the assistant (proposal_id set) were ever deducted here;
-- seeded history was not, so it is never refunded. hr_api cannot change status at all.
CREATE OR REPLACE FUNCTION refund_cancelled_leave() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE leave_balances SET available_days = available_days + OLD.business_days
    WHERE employee_id = OLD.employee_id AND leave_type = OLD.leave_type;
    RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS leave_requests_refund ON leave_requests;
CREATE TRIGGER leave_requests_refund AFTER UPDATE OF status ON leave_requests
    FOR EACH ROW
    WHEN (OLD.status IN ('pending_manager_review', 'approved')
          AND NEW.status = 'cancelled' AND OLD.proposal_id IS NOT NULL)
    EXECUTE FUNCTION refund_cancelled_leave();
"""


def create_schema(conn: psycopg.Connection, embedding_dimensions: int) -> None:
    """Create every table if it does not exist yet. Safe to run more than once."""
    dimensions = int(embedding_dimensions)
    if not 64 <= dimensions <= 4096:
        raise ValueError("embedding_dimensions must be between 64 and 4096")
    conn.execute(SCHEMA_SQL.format(dimensions=dimensions))


FRONT_MATTER_KEYS = ("document_id", "title", "version", "effective_date", "status")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_front_matter(lines: list[str], path: Path) -> tuple[dict[str, str], list[str]]:
    """Read `key: value` lines between the first two `---`. Values stay strings (\"2.1\", not 2.1)."""
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path.name}: missing front matter")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError(f"{path.name}: front matter is not closed") from None
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        if line.strip():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    missing = [key for key in FRONT_MATTER_KEYS if not meta.get(key)]
    if missing:
        raise ValueError(f"{path.name}: front matter missing {missing}")
    return meta, lines[end + 1 :]


# K9 option C: what the API account may do. Anything not listed is denied by PostgreSQL itself.
API_GRANTS = """
GRANT USAGE ON SCHEMA public TO {role};
REVOKE ALL ON employees, leave_balances, action_proposals, leave_requests,
              hr_tickets, policy_chunks, traces FROM {role};
GRANT SELECT ON employees, leave_balances, policy_chunks TO {role};
GRANT SELECT, INSERT ON action_proposals, leave_requests, traces TO {role};
GRANT UPDATE (confirmed_at) ON action_proposals TO {role};
GRANT UPDATE (available_days) ON leave_balances TO {role};  -- K26: lowering only, see the trigger
GRANT INSERT ON hr_tickets TO {role};

-- Row-level security: a second guard under the WHERE clauses in repository.py. The repository
-- sets app.employee_id (from the bearer token) at the start of every transaction on these three
-- tables. Unset means NULL, which matches no row: a query that forgets the identity sees nothing.
-- The table owner (hr_app, used by setup_lab) is not subject to these policies.
ALTER TABLE leave_requests ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS api_read ON leave_requests;
CREATE POLICY api_read ON leave_requests FOR SELECT TO {role} USING (
    employee_id = current_setting('app.employee_id', true)
    -- a manager also sees the requests of direct reports; an employee has none
    OR employee_id IN (SELECT employee_id FROM employees
                       WHERE manager_id = current_setting('app.employee_id', true))
);
DROP POLICY IF EXISTS api_insert_pending_only ON leave_requests;
CREATE POLICY api_insert_pending_only ON leave_requests FOR INSERT TO {role}
    WITH CHECK (status = 'pending_manager_review' AND status_set_by = 'assistant'
                AND employee_id = current_setting('app.employee_id', true));

-- Balances and proposals: own rows only, for every command. A manager never sees a report's balance.
ALTER TABLE leave_balances ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS api_own_balances ON leave_balances;
CREATE POLICY api_own_balances ON leave_balances FOR ALL TO {role}
    USING (employee_id = current_setting('app.employee_id', true))
    WITH CHECK (employee_id = current_setting('app.employee_id', true));

ALTER TABLE action_proposals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS api_own_proposals ON action_proposals;
CREATE POLICY api_own_proposals ON action_proposals FOR ALL TO {role}
    USING (employee_id = current_setting('app.employee_id', true))
    WITH CHECK (employee_id = current_setting('app.employee_id', true));
"""


def ensure_api_role(conn: psycopg.Connection, user: str, password: str) -> None:
    """Create or refresh the least-privilege login used by the API. Safe to run again.

    The role is server-wide, so it survives --reset; grants and policies are re-applied
    because DROP TABLE removes them.
    """
    role = sql.Identifier(user)
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,)).fetchone()
    verb = "ALTER" if exists else "CREATE"
    conn.execute(
        sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {}").format(
            role, sql.Literal(password)
        )
    )
    conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(conn.info.dbname), role))
    conn.execute(sql.SQL(API_GRANTS).format(role=role))


def chunk_policy(path: Path) -> list[dict[str, str]]:
    """Split one policy into one chunk per `## ` section.

    The same file always gives the same chunks: IDs come from document_id + section slug,
    not from order or randomness, and splitlines() makes CRLF and LF files identical.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    meta, body = parse_front_matter(lines, path)

    sections: list[tuple[str, list[str]]] = []
    for line in body:
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
        elif line.strip():
            raise ValueError(f"{path.name}: text before the first section")

    chunks: list[dict[str, str]] = []
    seen: set[str] = set()
    for section, content_lines in sections:
        chunk_id = f"{meta['document_id']}#{slugify(section)}"
        if chunk_id in seen:
            raise ValueError(f"{path.name}: duplicate section {section!r}")
        seen.add(chunk_id)
        chunk = {
            "chunk_id": chunk_id,
            "document_id": meta["document_id"],
            "title": meta["title"],
            "section": section,
            "version": meta["version"],
            "effective_date": meta["effective_date"],
            "status": meta["status"],
            "content": "\n".join(content_lines).strip(),
        }
        PolicyChunk.model_validate(chunk)  # fails loudly on a bad date, a bad status, or an empty field
        if not chunk["content"]:
            raise ValueError(f"{path.name}: section {section!r} is empty")
        chunks.append(chunk)
    if not chunks:
        raise ValueError(f"{path.name}: no sections found")
    return chunks


def load_json(name: str) -> list[dict[str, Any]]:
    rows = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"{name} must contain a JSON list")
    return rows


def drop_tables(conn: psycopg.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS " + ", ".join(TABLES))


def seed_employees(conn: psycopg.Connection, employees: list[dict[str, Any]], as_of: date) -> None:
    """Upsert identities; insert balances only when missing.

    K26: confirmations deduct from the stored balance, so after the first seed the database,
    not the JSON file, is the source of truth for balances. --reset restores the JSON values.
    """
    for row in employees:
        identity = AuthContext.model_validate(row)  # validates employee_id, display_name, role
        token = row.get("token")
        if not isinstance(token, str) or not token:
            raise ValueError(f"{identity.employee_id}: token is required")
        conn.execute(
            """
            INSERT INTO employees (employee_id, display_name, role, token_hash, department)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (employee_id) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                role = EXCLUDED.role,
                token_hash = EXCLUDED.token_hash,
                department = EXCLUDED.department
            """,
            (identity.employee_id, identity.display_name, identity.role, token_hash(token),
             row.get("department")),
        )
        for leave_type, days in row.get("balances", {}).items():
            balance = LeaveBalance(leave_type=leave_type, available_days=days, as_of_date=as_of)
            conn.execute(
                """
                INSERT INTO leave_balances (employee_id, leave_type, available_days, as_of_date)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (employee_id, leave_type) DO NOTHING
                """,
                (identity.employee_id, balance.leave_type, balance.available_days, balance.as_of_date),
            )
        # Atasan diisi setelah semua pegawai ada, supaya foreign key manager_id selalu menemukan
        # barisnya, apa pun urutan pegawai di file JSON.
    for row in employees:
        conn.execute(
            "UPDATE employees SET manager_id = %s WHERE employee_id = %s",
            (row.get("manager_id"), row["employee_id"]),
        )

def seed_historical_requests(conn: psycopg.Connection, requests: list[dict[str, Any]]) -> None:
    """Insert history once. Existing rows are never changed, because history is immutable."""
    for row in requests:
        request = LeaveRequestView.model_validate(row)
        employee_id = row.get("employee_id")
        if not isinstance(employee_id, str) or not employee_id:
            raise ValueError(f"{request.request_id}: employee_id is required")
        conn.execute(
            """
            INSERT INTO leave_requests (
                request_id, employee_id, leave_type, start_date, end_date,
                business_days, status, status_set_by, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'seed', %s)
            ON CONFLICT (request_id) DO NOTHING
            """,
            (
                request.request_id,
                employee_id,
                request.leave_type,
                request.start_date,
                request.end_date,
                request.business_days,
                request.status,
                request.created_at,
            ),
        )


def load_policy_chunks(policy_dir: Path | None = None) -> list[dict[str, str]]:
    """Every chunk of every policy file, in a stable order.

    K32: two files may never produce the same chunk_id. An archived version kept next to the
    current one with the same document_id would otherwise overwrite it in the upsert, silently.
    An archived version needs its own document_id.
    """
    chunks: list[dict[str, str]] = []
    seen: dict[str, str] = {}
    for path in sorted((policy_dir or DATA_DIR / "policies").glob("*.md")):
        for chunk in chunk_policy(path):
            if chunk["chunk_id"] in seen:
                raise ValueError(
                    f"{path.name}: {chunk['chunk_id']} is also in {seen[chunk['chunk_id']]}; "
                    "an archived version needs its own document_id"
                )
            seen[chunk["chunk_id"]] = path.name
            chunks.append(chunk)
    return chunks


def seed_policies(conn: psycopg.Connection) -> None:
    """Make policy_chunks match data/policies exactly.

    - New or changed sections are upserted, including their status (K32).
    - A section whose content changed loses its embedding (set to NULL), so it is re-embedded
      instead of answering with a vector of the old text.
    - Sections that no longer exist in the files are deleted.
    """
    chunks = load_policy_chunks()
    for chunk in chunks:
        conn.execute(
            """
            INSERT INTO policy_chunks (
                chunk_id, document_id, title, section, version, effective_date, content, status
            )
            VALUES (%(chunk_id)s, %(document_id)s, %(title)s, %(section)s,
                    %(version)s, %(effective_date)s, %(content)s, %(status)s)
            ON CONFLICT (chunk_id) DO UPDATE SET
                document_id = EXCLUDED.document_id,
                title = EXCLUDED.title,
                section = EXCLUDED.section,
                version = EXCLUDED.version,
                effective_date = EXCLUDED.effective_date,
                content = EXCLUDED.content,
                status = EXCLUDED.status,
                embedding = CASE
                    WHEN policy_chunks.content IS DISTINCT FROM EXCLUDED.content
                      OR policy_chunks.title IS DISTINCT FROM EXCLUDED.title
                      OR policy_chunks.section IS DISTINCT FROM EXCLUDED.section
                    THEN NULL
                    ELSE policy_chunks.embedding
                END
            """,
            chunk,
        )
    conn.execute(
        "DELETE FROM policy_chunks WHERE NOT (chunk_id = ANY(%s))",
        ([chunk["chunk_id"] for chunk in chunks],),
    )


def embedding_text(title: str, section: str, content: str) -> str:
    """Title and section give context the body lacks (\"Sisa cuti\" never says \"tahunan\")."""
    return f"{title}\n{section}\n{content}"


def embed_missing_chunks(conn: psycopg.Connection, provider: ModelProvider) -> int:
    """Embed only chunks whose embedding is NULL, so a repeated seed costs nothing."""
    rows = conn.execute(
        """
        SELECT chunk_id, title, section, content
        FROM policy_chunks
        WHERE embedding IS NULL
        ORDER BY chunk_id
        """
    ).fetchall()
    if not rows:
        return 0
    vectors = provider.embed([embedding_text(title, section, content) for _, title, section, content in rows])
    for (chunk_id, *_), vector in zip(rows, vectors, strict=True):
        conn.execute(
            "UPDATE policy_chunks SET embedding = %s::vector WHERE chunk_id = %s",
            (to_pgvector(vector), chunk_id),
        )
    return len(rows)


def count_rows(conn: psycopg.Connection) -> dict[str, int]:
    return {
        table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # table is a constant
        for table in ("employees", "leave_balances", "leave_requests", "policy_chunks")
    }


def reset_and_seed(reset: bool = False, provider: ModelProvider | None = None) -> dict[str, int]:
    """Seed in two transactions.

    1. Schema + identities + balances + history + policy text: all of it or nothing.
    2. Embeddings: needs the network. If it fails, part 1 is already saved and the next
       seed run only embeds what is still missing.
    """
    settings = get_settings()
    employees = load_json("employees.json")
    history = load_json("historical_requests.json")
    if provider is None and settings.openai_api_key and settings.embedding_model:
        provider = OpenAIProvider.from_settings(settings)

    with psycopg.connect(settings.database_url) as conn:
        if reset:
            drop_tables(conn)
        create_schema(conn, settings.embedding_dimensions)
        ensure_api_role(conn, settings.api_db_user, settings.api_db_password)
        seed_employees(conn, employees, as_of=today_wib())
        seed_historical_requests(conn, history)
        seed_policies(conn)
        conn.commit()

        embedded = embed_missing_chunks(conn, provider) if provider else 0
        conn.commit()

        counts = count_rows(conn)
        counts["embedded_now"] = embedded
        counts["chunks_without_embedding"] = conn.execute(
            "SELECT count(*) FROM policy_chunks WHERE embedding IS NULL"
        ).fetchone()[0]
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the schema and seed synthetic HR data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop every table first. Deletes proposals, requests, tickets, and traces.",
    )
    args = parser.parse_args()
    counts = reset_and_seed(reset=args.reset)
    mode = "reset + seed" if args.reset else "seed"
    print(f"{mode} selesai: " + ", ".join(f"{name}={n}" for name, n in counts.items()))
    if counts["chunks_without_embedding"]:
        print(
            "PERINGATAN: OPENAI_API_KEY atau EMBEDDING_MODEL kosong, sehingga "
            f"{counts['chunks_without_embedding']} chunk belum punya embedding. "
            "Vector search dan /readyz belum siap. Isi .env lalu jalankan seed lagi."
        )


if __name__ == "__main__":
    main()
