"""Endpointy twierdzeń, źródeł i decyzji redaktora."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from backend import schemas, services
from backend.db import get_db

router = APIRouter(prefix="/api", tags=["twierdzenia i źródła"])


@router.get("/claims/{claim_id}", response_model=schemas.ClaimOut)
def get_claim(claim_id: int, db: Session = Depends(get_db)):
    return services.get_claim(db, claim_id)


@router.patch("/claims/{claim_id}", response_model=schemas.ClaimOut)
def update_claim(claim_id: int, data: schemas.ClaimUpdate, db: Session = Depends(get_db)):
    return services.update_claim(db, claim_id, data)


@router.delete("/claims/{claim_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_claim(claim_id: int, db: Session = Depends(get_db)):
    services.delete_claim(db, claim_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/claims/{claim_id}/decisions", response_model=list[schemas.EditorDecisionOut])
def list_decisions(claim_id: int, db: Session = Depends(get_db)):
    return services.get_claim(db, claim_id).decisions


@router.post("/claims/{claim_id}/decisions", response_model=schemas.EditorDecisionOut,
             status_code=status.HTTP_201_CREATED)
def add_decision(claim_id: int, data: schemas.EditorDecisionIn, db: Session = Depends(get_db)):
    """Redaktor ma ostatnie słowo — nadpisanie werdyktu z notatką; historia jest zachowywana."""
    return services.add_editor_decision(db, claim_id, data)


@router.get("/sources", response_model=list[schemas.SourceOut])
def list_sources(db: Session = Depends(get_db)):
    return services.list_sources(db)


@router.get("/sources/{source_id}", response_model=schemas.SourceOut)
def get_source(source_id: int, db: Session = Depends(get_db)):
    return services.get_source(db, source_id)
