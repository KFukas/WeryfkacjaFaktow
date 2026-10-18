"""Endpointy przebiegów agenta: uruchomienie weryfikacji, postęp na żywo (SSE), audyt."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import schemas, services
from backend.db import get_db, session_scope
from backend.models import AgentEvent, AgentRun

router = APIRouter(prefix="/api", tags=["agent i audyt"])
FINISHED = {"completed", "failed", "budget_exceeded"}


def _launch(article_id: int, claim_id: int | None, key: str | None) -> AgentRun:
    from orchestrator import runner

    run_id, created = runner.create_run(article_id, claim_id, key)
    if created:
        runner.start_background(run_id, article_id, claim_id)
    with session_scope() as db:
        return services.get_run(db, run_id)


@router.post("/articles/{article_id}/verify", response_model=schemas.AgentRunOut, status_code=202)
def verify_article(article_id: int, body: schemas.VerifyRequest | None = None):
    """Uruchamia weryfikację artykułu w tle. Idempotentne: trwający przebieg / ten sam klucz zwraca istniejący."""
    return _launch(article_id, None, body.idempotency_key if body else None)


@router.post("/claims/{claim_id}/reverify", response_model=schemas.AgentRunOut, status_code=202)
def reverify_claim(claim_id: int, body: schemas.VerifyRequest | None = None, db: Session = Depends(get_db)):
    """Ponowna weryfikacja pojedynczego twierdzenia (źródła agenta są czyszczone, decyzje redaktora zostają)."""
    claim = services.get_claim(db, claim_id)
    return _launch(claim.article_id, claim_id, body.idempotency_key if body else None)


@router.get("/runs", response_model=list[schemas.AgentRunOut])
def list_runs(article_id: int | None = None, limit: int = Query(default=50, le=500), db: Session = Depends(get_db)):
    stmt = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
    if article_id is not None:
        stmt = stmt.where(AgentRun.article_id == article_id)
    return list(db.scalars(stmt))


@router.get("/runs/{run_id}", response_model=schemas.AgentRunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    return services.get_run(db, run_id)


@router.get("/runs/{run_id}/events", response_model=list[schemas.AgentEventOut])
def run_events(run_id: str, after_id: int = 0, db: Session = Depends(get_db)):
    services.get_run(db, run_id)
    stmt = select(AgentEvent).where(AgentEvent.run_id == run_id, AgentEvent.id > after_id).order_by(AgentEvent.id)
    return list(db.scalars(stmt))


@router.get("/runs/{run_id}/stream")
async def run_stream(run_id: str, request: Request):
    """Server-Sent Events: zdarzenia przebiegu na żywo (event: agent), na końcu `event: end`."""
    with session_scope() as db:
        services.get_run(db, run_id)

    async def gen():
        last_id, idle = 0, 0
        while True:
            if await request.is_disconnected():
                return
            with session_scope() as db:
                events = list(db.scalars(select(AgentEvent).where(AgentEvent.run_id == run_id,
                                                                  AgentEvent.id > last_id).order_by(AgentEvent.id)))
                run = db.get(AgentRun, run_id)
                status = run.status if run else "failed"
                payloads = [schemas.AgentEventOut.model_validate(e).model_dump(mode="json") for e in events]
                run_json = schemas.AgentRunOut.model_validate(run).model_dump(mode="json") if run else {}
            for p in payloads:
                last_id = p["id"]
                p["payload"] = {k: v for k, v in p["payload"].items() if k not in ("user_prompt", "response")}
                yield f"id: {p['id']}\nevent: agent\ndata: {json.dumps(p, ensure_ascii=False)}\n\n"
            if status in FINISHED and not payloads:
                yield f"event: end\ndata: {json.dumps(run_json, ensure_ascii=False)}\n\n"
                return
            idle = 0 if payloads else idle + 1
            if idle and idle % 30 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
