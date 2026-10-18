"""Aplikacja FastAPI redakcji „Kurier Faktów”."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import services
from backend.config import get_settings
from backend.db import ensure_schema
from backend.routers import articles, claims, runs


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Migracje przy starcie (idempotentne) — działa tak samo dla SQLite i PostgreSQL.
    ensure_schema()
    yield


app = FastAPI(
    title="Kurier Faktów — API weryfikacji faktów",
    version="1.0.0",
    description="REST API redakcji: artykuły, twierdzenia, źródła, przebiegi agenta i decyzje redaktora.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(services.NotFound)
async def _not_found(_req: Request, exc: services.NotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(services.DomainError)
async def _domain_error(_req: Request, exc: services.DomainError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/api/health", tags=["system"])
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "llm_provider": s.llm_provider, "model": s.anthropic_model,
            "sandbox_transport": s.web_sandbox_transport}


app.include_router(articles.router)
app.include_router(claims.router)
app.include_router(runs.router)
