"""Logika narzędzi sandboksa (bez warstwy MCP — łatwa do testowania)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from mcp_servers.web_sandbox import sanitizer, scoring
from mcp_servers.web_sandbox.netguard import FetchError, Guard, safe_fetch
from mcp_servers.web_sandbox.providers import Providers
from mcp_servers.web_sandbox.settings import SandboxSettings


class SandboxTools:
    def __init__(self, settings: SandboxSettings | None = None, guard: Guard | None = None):
        self.settings = settings or SandboxSettings.from_env()
        self.guard = guard or Guard(self.settings)
        self.providers = Providers(self.settings)

    @staticmethod
    def _error(code: str, message: str, **extra: Any) -> dict:
        return {"error": code, "message": message, "untrusted": True, **extra}

    def search_public_sources(self, query: str, source_types: list[str] | None = None, lang: str = "pl",
                              limit: int = 8) -> dict:
        query = (query or "").strip()[:300]
        if not query:
            return self._error("invalid_query", "puste zapytanie")
        return self.providers.search(query, source_types, lang, max(1, min(int(limit), 20)))

    def query_dataset(self, provider: str, dataset_id: str, params: dict[str, Any] | None = None) -> dict:
        try:
            return self.providers.query(provider, dataset_id, params)
        except FetchError as exc:
            return self._error(exc.code, exc.message, provider=provider, dataset_id=dataset_id)

    def fetch_url_sanitized(self, url: str) -> dict:
        url = (url or "").strip()
        try:
            host, port = self.guard.validate_url(url)
        except FetchError as exc:
            return self._error(exc.code, exc.message, url=url)
        fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
        max_chars = self.settings.max_text_chars
        if self.settings.offline:
            page = self.providers.offline_page(url)
            if page is not None:
                content, ctype = page
                res = sanitizer.sanitize("html" if "html" in ctype else "text", content.encode("utf-8"),
                                         max_chars=max_chars)
                env = res.envelope(url, url, fetched_at, content.encode("utf-8"), ctype)
                env["mode"] = "offline"
                return env
            if (host, port) not in self.settings.test_allow:
                return self._error("offline_unavailable", "tryb offline: strona niedostępna w archiwum", url=url)
        try:
            result = safe_fetch(url, self.settings, self.guard)
        except FetchError as exc:
            return self._error(exc.code, exc.message, url=url)
        res = sanitizer.sanitize(result.kind, result.body, result.encoding, max_chars=max_chars)
        env = res.envelope(url, result.final_url, fetched_at, result.body, result.content_type)
        env["redirects"] = result.redirects
        env["mode"] = "online"
        final_host = urlsplit(result.final_url).hostname or ""
        if scoring.registrable(final_host) != scoring.registrable(host):
            env["injection_flags"].append({"type": "cross_domain_redirect", "severity": "low", "channel": "http",
                                           "evidence": f"przekierowanie na {final_host}"})
        return env

    def score_source(self, url: str, metadata: dict[str, Any] | None = None) -> dict:
        if not url or not isinstance(url, str):
            return self._error("invalid_url", "brak URL")
        return scoring.score_source(url, metadata or {}, str(self.settings.rubric_path))
