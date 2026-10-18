"""Serwer MCP „newsroom” — strefa ZAUFANA (baza redakcji).

Wywoływany wyłącznie przez orkiestrator (i redaktora w Claude Code). Model nigdy nie dostaje tych narzędzi
w etapach, w których widzi treść z sieci. Cała walidacja jest w `backend.services` (wspólna z REST API).

  python -m mcp_servers.newsroom.server        # stdio
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from pydantic import ValidationError

from backend import schemas, services
from backend.db import Base, get_engine, session_scope

server = MCPServer(
    name="newsroom",
    title="Kurier Faktów — baza redakcji (strefa zaufana)",
    instructions="Odczyt artykułów i zapis wyników weryfikacji. Werdykty są walidowane (enum, pewność 0–1, "
                 "wymagane źródło wspierające/przeczące).",
    version="1.0.0",
)


def _err(exc: Exception) -> dict[str, Any]:
    code = "not_found" if isinstance(exc, services.NotFound) else "validation_error"
    return {"error": code, "message": str(exc)[:1000]}


def _claim_dict(c) -> dict[str, Any]:
    return {"id": c.id, "article_id": c.article_id, "text": c.text, "start_offset": c.start_offset,
            "end_offset": c.end_offset, "category": c.category, "verdict": c.verdict,
            "effective_verdict": c.effective_verdict, "confidence": c.confidence}


@server.tool()
def get_article(article_id: int) -> dict[str, Any]:
    """Zwraca artykuł (id, title, body, author, status) wraz z istniejącymi twierdzeniami."""
    try:
        with session_scope() as db:
            a = services.get_article(db, article_id)
            return {"id": a.id, "title": a.title, "body": a.body, "author": a.author, "status": a.status,
                    "claims": [_claim_dict(c) for c in a.claims]}
    except services.NotFound as exc:
        return _err(exc)


@server.tool()
def list_pending_articles() -> dict[str, Any]:
    """Artykuły oczekujące na weryfikację (status draft lub in_review)."""
    with session_scope() as db:
        return {"articles": [{"id": a.id, "title": a.title, "status": a.status}
                             for a in services.list_pending_articles(db)]}


@server.tool()
def save_claims(article_id: int, claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Zapisuje twierdzenia z offsetami start/end (tekst musi występować w artykule). Idempotentne."""
    try:
        parsed = [schemas.ClaimIn.model_validate(c) for c in claims]
        with session_scope() as db:
            return {"claims": [_claim_dict(c) for c in services.save_claims(db, article_id, parsed)]}
    except (ValidationError, services.DomainError, services.NotFound) as exc:
        return _err(exc)


@server.tool()
def attach_source(claim_id: int, source: dict[str, Any], relation: str, quote: str = "",
                  quote_verified: bool = False) -> dict[str, Any]:
    """Dołącza źródło do twierdzenia z relacją supports|contradicts|context i cytatem."""
    try:
        data = schemas.AttachSourceIn(source=schemas.SourceIn.model_validate(source), relation=relation,
                                      quote=quote, quote_verified=quote_verified)
        with session_scope() as db:
            link = services.attach_source(db, claim_id, data)
            return {"claim_source_id": link.id, "source_id": link.source_id, "relation": link.relation}
    except (ValidationError, services.DomainError, services.NotFound) as exc:
        return _err(exc)


@server.tool()
def save_verdict(claim_id: int, verdict: str, confidence: float, rationale: str,
                 details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Zapisuje werdykt: potwierdzone|wątpliwe|fałszywe, pewność 0–1, uzasadnienie; walidacja źródeł."""
    try:
        data = schemas.VerdictIn(verdict=verdict, confidence=confidence, rationale=rationale, details=details or {})
        with session_scope() as db:
            return _claim_dict(services.save_verdict(db, claim_id, data))
    except (ValidationError, services.DomainError, services.NotFound) as exc:
        return _err(exc)


@server.tool()
def log_agent_event(run_id: str, event: dict[str, Any]) -> dict[str, Any]:
    """Zapis zdarzenia audytu (krok, wywołanie narzędzia, prompt, tokeny, koszt) dla przebiegu agenta."""
    try:
        ev = schemas.AgentEventIn.model_validate(event)
        with session_scope() as db:
            return {"id": services.log_agent_event(db, run_id, ev).id}
    except (ValidationError, services.NotFound) as exc:
        return _err(exc)


def main() -> None:
    Base.metadata.create_all(get_engine())
    server.run("stdio")


if __name__ == "__main__":
    main()
