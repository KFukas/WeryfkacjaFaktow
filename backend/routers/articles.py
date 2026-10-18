"""Endpointy artykułów i raportów."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from backend import schemas, services
from backend.db import get_db

router = APIRouter(prefix="/api/articles", tags=["artykuły"])


def _summary(art) -> schemas.ArticleSummary:
    out = schemas.ArticleSummary.model_validate(art)
    out.claim_counts = services.claim_counts(art)
    return out


@router.get("", response_model=list[schemas.ArticleSummary])
def list_articles(status_: str | None = Query(default=None, alias="status"), db: Session = Depends(get_db)):
    return [_summary(a) for a in services.list_articles(db, status_)]


@router.post("", response_model=schemas.ArticleOut, status_code=status.HTTP_201_CREATED)
def create_article(data: schemas.ArticleCreate, db: Session = Depends(get_db)):
    art = services.create_article(db, data)
    return schemas.ArticleOut.model_validate(art)


@router.get("/{article_id}", response_model=schemas.ArticleOut)
def get_article(article_id: int, db: Session = Depends(get_db)):
    art = services.get_article(db, article_id)
    out = schemas.ArticleOut.model_validate(art)
    out.claim_counts = services.claim_counts(art)
    return out


@router.patch("/{article_id}", response_model=schemas.ArticleOut)
def update_article(article_id: int, data: schemas.ArticleUpdate, db: Session = Depends(get_db)):
    return schemas.ArticleOut.model_validate(services.update_article(db, article_id, data))


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(article_id: int, db: Session = Depends(get_db)):
    services.delete_article(db, article_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{article_id}/claims", response_model=list[schemas.ClaimOut])
def list_claims(article_id: int, db: Session = Depends(get_db)):
    return services.get_article(db, article_id).claims


@router.post("/{article_id}/claims", response_model=list[schemas.ClaimOut], status_code=status.HTTP_201_CREATED)
def add_claims(article_id: int, claims: list[schemas.ClaimIn], db: Session = Depends(get_db)):
    """Ręczne dodanie twierdzeń przez redaktora (offsety są weryfikowane z treścią artykułu)."""
    return services.save_claims(db, article_id, claims)


@router.get("/{article_id}/report")
def report(article_id: int, format: Literal["md", "json"] = "md", db: Session = Depends(get_db)):
    art = services.get_article(db, article_id)
    if format == "json":
        return services.report_json(art)
    return Response(
        content=services.report_markdown(art),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="raport-artykul-{art.id}.md"'},
    )
