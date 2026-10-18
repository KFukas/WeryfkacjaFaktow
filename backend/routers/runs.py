"""Endpointy przebiegów agenta i audytu."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import schemas, services
from backend.db import get_db
from backend.models import AgentEvent, AgentRun

router = APIRouter(prefix="/api", tags=["agent i audyt"])


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
