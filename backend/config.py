"""Konfiguracja strefy zaufanej (API, orkiestrator, newsroom MCP) z `.env` / zmiennych środowiskowych."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = f"sqlite:///{(ROOT_DIR / 'data' / 'kurier.db').as_posix()}"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080"

    # LLM
    llm_provider: str = "mock"  # mock | anthropic | gullible (tylko testy)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_quarantine_model: str = ""
    anthropic_effort: str = "medium"
    anthropic_fallbacks: str = "default"  # default | off

    # Limity orkiestratora (na artykuł)
    agent_max_claims: int = 12
    agent_max_tool_calls: int = 60
    agent_max_cost_usd: float = 1.50
    agent_max_sources_per_claim: int = 4

    # Sandbox
    web_sandbox_transport: str = "stdio"  # stdio | http | inproc (testy)
    web_sandbox_url: str = "http://mcp-web-sandbox:8765/mcp"
    sandbox_offline: str = "1"
    sandbox_test_allow: str = ""

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
