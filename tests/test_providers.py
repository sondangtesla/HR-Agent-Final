"""OpenAIProvider configuration that only shows up inside Docker Compose."""
from __future__ import annotations

import pytest

from src.config import Settings
from src.providers import OpenAIProvider


def make(settings: Settings) -> OpenAIProvider:
    return OpenAIProvider.from_settings(settings)


def test_empty_base_url_from_compose_falls_back_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compose passes OPENAI_BASE_URL="" when .env leaves it blank. The SDK must not use "" as the
    server address (clean-checkout Docker run, 10 Nov 2026: seed failed with "missing http://")."""
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    settings = Settings(openai_api_key="test-key", agent_model="m", embedding_model="e",
                        openai_base_url="", _env_file=None)
    assert str(make(settings).client.base_url) == "https://api.openai.com/v1/"


def test_configured_base_url_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    settings = Settings(openai_api_key="test-key", agent_model="m", embedding_model="e",
                        openai_base_url="https://proxy.example.test/v1", _env_file=None)
    assert str(make(settings).client.base_url) == "https://proxy.example.test/v1/"
