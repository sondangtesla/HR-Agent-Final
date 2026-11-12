from __future__ import annotations

import hashlib
import logging
from datetime import date

from pydantic import ValidationError

from .cache import ResilientCache
from .contracts import PolicyChunk
from .domain import today_wib
from .providers import ModelProvider
from .repository import Repository
from .text import tokenize

logger = logging.getLogger(__name__)

RRF_K = 60  # standard reciprocal-rank-fusion constant
CANDIDATES_PER_SOURCE = 10
# A chunk that contains every query word gains as much as one extra rank-1 vote.
KEYWORD_WEIGHT = 1 / (RRF_K + 1)


class RetrievalService:
    def __init__(
        self,
        repository: Repository,
        provider: ModelProvider,
        cache: ResilientCache,
        cache_ttl_seconds: int,
        index_version: str = "unversioned",
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds
        self.index_version = index_version

    def cache_key(self, query: str, top_k: int, as_of: date | None = None) -> str:
        """The index version is part of the key, so a reindex never serves old chunks.

        The day is part of it too (K32): a policy that comes into force today is never hidden
        behind yesterday's cached result. The query is hashed: the key stays short and raw user
        text never lands in Redis keys.
        """
        normalized = " ".join(query.lower().split())
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        day = (as_of or today_wib()).isoformat()
        return f"retrieval:{self.index_version}:{day}:{top_k}:{digest}"

    def search(self, query: str, top_k: int = 3, as_of: date | None = None) -> list[PolicyChunk]:
        """Top chunks among the policies in force on `as_of` (default: today in WIB)."""
        as_of = as_of or today_wib()
        key = self.cache_key(query, top_k, as_of)
        cached = self.cache.get(key)
        if cached is not None:
            try:
                return [PolicyChunk.model_validate(item) for item in cached]
            except (ValidationError, TypeError):
                logger.warning("cached retrieval result is malformed; treating as miss")

        lexical = self.repository.lexical_search(query, CANDIDATES_PER_SOURCE, as_of)
        degraded = False
        try:
            query_vector = self.provider.embed([query])[0]
            semantic = self.repository.vector_search(query_vector, CANDIDATES_PER_SOURCE, as_of)
        except Exception as exc:  # embedding provider down: keep answering with lexical only
            logger.warning("vector search unavailable (%s); using lexical only", type(exc).__name__)
            semantic, degraded = [], True

        results = self.fuse(query, lexical, semantic)[:top_k]
        if not degraded:  # never cache a degraded answer for the whole TTL
            self.cache.set(key, [chunk.model_dump(mode="json") for chunk in results], self.cache_ttl_seconds)
        return results

    @staticmethod
    def fuse(query: str, lexical: list[PolicyChunk], semantic: list[PolicyChunk]) -> list[PolicyChunk]:
        """Reciprocal-rank fusion, then a keyword bonus.

        RRF uses ranks, not raw scores, because ts_rank and cosine similarity live on
        different scales. The keyword bonus counts query words found in the section body;
        the title is left out because every section of a document shares it.
        """
        scores: dict[str, float] = {}
        chunks: dict[str, PolicyChunk] = {}
        for ranked in (lexical, semantic):
            for rank, chunk in enumerate(ranked, start=1):
                scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1 / (RRF_K + rank)
                chunks.setdefault(chunk.chunk_id, chunk)

        terms = tokenize(query)
        if terms:
            for chunk_id, chunk in chunks.items():
                words = set(tokenize(f"{chunk.section} {chunk.content}"))
                coverage = sum(term in words for term in terms) / len(terms)
                scores[chunk_id] += KEYWORD_WEIGHT * coverage

        ordered = sorted(chunks, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
        return [chunks[cid].model_copy(update={"score": round(scores[cid], 6)}) for cid in ordered]
