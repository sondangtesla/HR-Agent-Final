"""Retrieval only ever sees policies in force (status "berlaku", effective_date reached)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.cache import NullCache
from src.contracts import PolicyChunk
from src.providers import DeterministicProvider
from src.repository import MemoryRepository
from src.retrieval import RetrievalService
from src.setup_lab import chunk_policy, load_policy_chunks

TODAY = date(2026, 9, 23)
QUERY = "jatah cuti tahunan"


def write_policy(folder: Path, name: str, front: str, body: str = "## Hak dan saldo\n\nIsi.\n") -> Path:
    path = folder / name
    path.write_text(f"---\n{front}\n---\n{body}", encoding="utf-8")
    return path


# --- Seed: status comes from the document, explicitly ---

def test_every_supplied_policy_declares_its_status() -> None:
    chunks = load_policy_chunks()
    assert len(chunks) == 15
    assert {chunk["status"] for chunk in chunks} == {"berlaku"}


def test_a_policy_without_status_fails_loudly(tmp_path: Path) -> None:
    path = write_policy(tmp_path, "a.md", "document_id: HR-X-001\ntitle: X\nversion: 1.0\neffective_date: 2026-01-01")
    with pytest.raises(ValueError, match="status"):
        chunk_policy(path)


def test_a_policy_with_an_unknown_status_fails_loudly(tmp_path: Path) -> None:
    path = write_policy(tmp_path, "a.md", "document_id: HR-X-001\ntitle: X\nversion: 1.0\n"
                                          "effective_date: 2026-01-01\nstatus: draft")
    with pytest.raises(ValueError):
        chunk_policy(path)


def test_an_archived_copy_can_never_overwrite_the_current_document(tmp_path: Path) -> None:
    """Same document_id + section in two files = same chunk_id; the upsert would keep only one."""
    write_policy(tmp_path, "annual.md", "document_id: HR-X-001\ntitle: X\nversion: 2.1\n"
                                        "effective_date: 2026-01-01\nstatus: berlaku")
    write_policy(tmp_path, "annual-old.md", "document_id: HR-X-001\ntitle: X\nversion: 2.0\n"
                                            "effective_date: 2025-01-01\nstatus: arsip")
    with pytest.raises(ValueError, match="own document_id"):
        load_policy_chunks(tmp_path)


# --- Retrieval: filtered before ranking, in both lexical and vector search ---

def chunk(chunk_id: str, document_id: str, content: str, *, status: str = "berlaku",
          effective: date = date(2026, 1, 1)) -> PolicyChunk:
    return PolicyChunk(chunk_id=chunk_id, document_id=document_id, title="Kebijakan Cuti Tahunan",
                       section="Hak dan saldo", version="1.0", effective_date=effective,
                       content=content, status=status)


@pytest.fixture
def repo_with_old_and_future() -> MemoryRepository:
    repo = MemoryRepository()
    repo.chunks = [
        chunk("now", "HR-LEAVE-001", "Pegawai memperoleh 12 hari cuti tahunan."),
        # Both match the query better than the policy in force, and both have its exact vector:
        chunk("old", "HR-LEAVE-OLD", "Jatah cuti tahunan 15 hari cuti tahunan jatah.", status="arsip",
              effective=date(2025, 1, 1)),
        chunk("future", "HR-LEAVE-NEW", "Jatah cuti tahunan 14 hari cuti tahunan jatah.",
              effective=date(2027, 1, 1)),
    ]
    vector = DeterministicProvider().embed([QUERY])[0]
    repo.embeddings = {c.chunk_id: vector for c in repo.chunks}
    return repo


def test_archived_and_future_policies_are_never_retrieved(repo_with_old_and_future: MemoryRepository) -> None:
    repo = repo_with_old_and_future
    assert [c.chunk_id for c in repo.lexical_search(QUERY, 10, TODAY)] == ["now"]
    assert [c.chunk_id for c in repo.vector_search(DeterministicProvider().embed([QUERY])[0], 10, TODAY)] == ["now"]
    service = RetrievalService(repo, DeterministicProvider(), NullCache(), 0)
    assert [c.document_id for c in service.search(QUERY, top_k=3, as_of=TODAY)] == ["HR-LEAVE-001"]


def test_a_policy_is_retrievable_from_its_effective_date(repo_with_old_and_future: MemoryRepository) -> None:
    repo = repo_with_old_and_future
    assert "future" not in {c.chunk_id for c in repo.lexical_search(QUERY, 10, date(2026, 12, 31))}
    assert "future" in {c.chunk_id for c in repo.lexical_search(QUERY, 10, date(2027, 1, 1))}


def test_cached_results_are_per_day() -> None:
    service = RetrievalService(MemoryRepository(), DeterministicProvider(), NullCache(), 0)
    assert service.cache_key(QUERY, 3, date(2026, 12, 31)) != service.cache_key(QUERY, 3, date(2027, 1, 1))
