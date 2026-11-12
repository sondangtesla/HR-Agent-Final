from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import psycopg
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg_pool import PoolTimeout
from starlette.exceptions import HTTPException as StarletteHTTPException

from .agent import AgentService
from .cache import ResilientCache
from .config import Settings, get_settings
from .contracts import (
    ActionResult,
    AuthContext,
    ChatRequest,
    ChatResponse,
    ConfirmActionRequest,
    LeaveRequestView,
    ProblemDetail,
)
from .conversation import ConversationStore
from .monitoring import evaluate_alerts, load_rules
from .providers import DeterministicProvider, ModelProvider, OpenAIProvider, UnavailableProvider
from .repository import ConflictError, PostgresRepository, Repository
from .retrieval import RetrievalService
from .tools import ToolExecutor

logger = logging.getLogger(__name__)


@dataclass
class Runtime:
    repository: Repository
    cache: ResilientCache
    provider: ModelProvider
    agent: AgentService


def build_provider(settings: Settings) -> ModelProvider:
    if settings.model_mode == "fake":
        return DeterministicProvider(settings.embedding_dimensions)
    if settings.live_model_ready:
        return OpenAIProvider.from_settings(settings)
    logger.warning("live model not configured; chat will abstain until OPENAI_API_KEY and models are set")
    return UnavailableProvider()


def build_runtime(settings: Settings) -> Runtime:
    # The API never logs in as hr_app (superuser): it uses the least-privilege hr_api account.
    repository = PostgresRepository(settings.api_database_url, settings.embedding_dimensions)
    cache = ResilientCache(settings.redis_url)
    provider = build_provider(settings)
    retrieval = RetrievalService(
        repository, provider, cache, settings.retrieval_cache_ttl_seconds,
        index_version=settings.policy_index_version,
    )
    tools = ToolExecutor(repository, retrieval, settings)
    # Memory and ticket drafts (K25) share the Redis client; if Redis dies, no ticket can be sent.
    agent = AgentService(repository, provider, tools, settings, conversation=ConversationStore(cache))
    return Runtime(repository, cache, provider, agent)


class ApiError(Exception):
    def __init__(self, status: int, title: str, detail: str, headers: dict[str, str] | None = None) -> None:
        self.status, self.title, self.detail, self.headers = status, title, detail, headers


def problem(status: int, title: str, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    """RFC 7807 problem detail. Never a stack trace, prompt, secret, or another user's data."""
    body = ProblemDetail(title=title, status=status, detail=detail).model_dump()
    return JSONResponse(body, status_code=status, headers=headers, media_type="application/problem+json")


def create_app(*, settings: Settings | None = None, repository=None, cache=None, agent=None) -> FastAPI:
    """Build the documented API without changing endpoint or response contracts."""
    settings = settings or get_settings()
    if repository is None or cache is None or agent is None:
        runtime = build_runtime(settings)
        repository = repository or runtime.repository
        cache = cache or runtime.cache
        agent = agent or runtime.agent
    rules = load_rules()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        close = getattr(repository, "close", None)
        if callable(close):
            close()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    # --- Error handling: one consistent problem-detail shape for every failure ---

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return problem(exc.status, exc.title, exc.detail, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem(exc.status_code, "HTTP error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Field locations only: FastAPI's default echoes the submitted value, which may hold PII.
        fields = sorted({".".join(str(part) for part in err["loc"]) for err in exc.errors()})
        return problem(422, "Request tidak valid", f"Periksa field: {', '.join(fields)}")

    @app.exception_handler(psycopg.Error)
    @app.exception_handler(PoolTimeout)
    async def _database_unavailable(_: Request, exc: Exception) -> JSONResponse:
        logger.warning("database unavailable (%s)", type(exc).__name__)
        return problem(503, "Layanan tidak tersedia", "Database sedang tidak dapat dihubungi. Coba lagi nanti.",
                       {"Retry-After": "10"})

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        incident = uuid.uuid4().hex[:12]
        logger.error("unhandled %s (incident %s)", type(exc).__name__, incident)
        return problem(500, "Kesalahan internal", f"Terjadi kesalahan. Referensi insiden: {incident}.")

    # --- Authentication: identity comes only from the bearer token ---

    bearer = HTTPBearer(auto_error=False)  # auto_error=True would answer 403, the contract says 401

    def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> AuthContext:
        unauthorized = ApiError(401, "Tidak terautentikasi", "Token bearer tidak ada atau tidak valid.",
                                {"WWW-Authenticate": "Bearer"})
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise unauthorized
        auth = repository.authenticate(credentials.credentials)
        if auth is None:
            raise unauthorized
        return auth

    def monitoring_admin(auth: AuthContext = Depends(current_user)) -> AuthContext:
        if auth.role != "monitoring_admin":
            raise ApiError(403, "Akses ditolak", "Hanya monitoring admin yang boleh membuka monitoring.")
        return auth

    # --- Health ---

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        checks: dict[str, str] = {}
        database_ok = repository.health()
        checks["database"] = "ok" if database_ok else "fail"
        if database_ok:
            try:
                index = repository.index_status()
                checks["index"] = (
                    "ok" if index["chunks"] and not index["missing_embeddings"]
                    else "empty" if not index["chunks"] else "missing_embeddings"
                )
            except psycopg.errors.UndefinedColumn:
                checks["index"] = "schema_outdated"
        else:
            checks["index"] = "unknown"
        checks["cache"] = "ok" if cache.health() else "degraded"  # Redis may die; never blocks readiness
        checks["model"] = "ok" if settings.model_mode == "fake" or settings.live_model_ready else "missing_config"
        ready = checks["database"] == "ok" and checks["index"] == "ok" and checks["model"] == "ok"
        return JSONResponse({"status": "ready" if ready else "not_ready", "checks": checks},
                            status_code=200 if ready else 503)

    # --- API v1 ---

    @app.post("/api/v1/chat", response_model=ChatResponse)
    def chat(body: ChatRequest, auth: AuthContext = Depends(current_user)) -> ChatResponse:
        return agent.run(body, auth)

    @app.post("/api/v1/action-proposals/{proposal_id}/confirm", response_model=ActionResult)
    def confirm(proposal_id: str, body: ConfirmActionRequest, auth: AuthContext = Depends(current_user)) -> ActionResult:
        try:
            return repository.confirm_proposal(auth.employee_id, proposal_id, body.idempotency_key)
        except KeyError:
            # Same answer for "does not exist" and "belongs to someone else": no existence leak.
            raise ApiError(404, "Tidak ditemukan", "Proposal tidak ditemukan.") from None
        except ConflictError as exc:
            raise ApiError(409, "Konflik", str(exc)) from None

    @app.get("/api/v1/leave-requests/me", response_model=list[LeaveRequestView])
    def my_requests(auth: AuthContext = Depends(current_user)) -> list[LeaveRequestView]:
        return repository.list_leave_requests(auth.employee_id)

    @app.get("/api/v1/traces/{trace_id}")
    def get_trace(trace_id: str, auth: AuthContext = Depends(current_user)) -> dict[str, Any]:
        trace = repository.get_trace(trace_id)
        if trace is None:
            raise ApiError(404, "Tidak ditemukan", "Trace tidak ditemukan.")
        if trace["employee_id"] != auth.employee_id and auth.role != "monitoring_admin":
            raise ApiError(403, "Akses ditolak", "Trace ini milik pengguna lain.")
        return trace

    @app.get("/api/v1/monitoring/summary")
    def monitoring_summary(_: AuthContext = Depends(monitoring_admin)) -> dict[str, Any]:
        return repository.monitoring_summary()

    @app.get("/api/v1/monitoring/alerts")
    def monitoring_alerts(_: AuthContext = Depends(monitoring_admin)) -> list[dict[str, Any]]:
        return evaluate_alerts(repository.monitoring_summary(), rules)

    return app
