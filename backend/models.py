"""Model danych redakcji: artykuły, twierdzenia, źródła, audyt agenta, decyzje redaktora."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

ARTICLE_STATUSES = ("draft", "in_review", "verified")
VERDICTS = ("potwierdzone", "wątpliwe", "fałszywe", "oczekuje")
FINAL_VERDICTS = ("potwierdzone", "wątpliwe", "fałszywe")
CLAIM_CATEGORIES = ("liczbowe", "datowe", "cytat", "przyczynowe", "porównawcze", "inne")
RELATIONS = ("supports", "contradicts", "context")
RUN_STATUSES = ("queued", "running", "completed", "failed", "budget_exceeded")


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    claims: Mapped[list[Claim]] = relationship(
        back_populates="article", cascade="all, delete-orphan", order_by="Claim.start_offset"
    )
    runs: Mapped[list[AgentRun]] = relationship(back_populates="article", cascade="all, delete-orphan")


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(20), default="inne")
    verdict: Mapped[str] = mapped_column(String(20), default="oczekuje")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Czy werdykt został obniżony przez reguły deterministyczne / ostrzeżenia bezpieczeństwa
    verdict_details: Mapped[dict] = mapped_column(JSON, default=dict)

    article: Mapped[Article] = relationship(back_populates="claims")
    sources: Mapped[list[ClaimSource]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    decisions: Mapped[list[EditorDecision]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="EditorDecision.created_at"
    )

    @property
    def latest_decision(self) -> EditorDecision | None:
        return self.decisions[-1] if self.decisions else None

    @property
    def effective_verdict(self) -> str:
        """Redaktor ma ostatnie słowo: ostatnia decyzja nadpisuje werdykt agenta."""
        d = self.latest_decision
        return d.override_verdict if d and d.override_verdict else self.verdict


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("url", "content_sha256", name="uq_source_url_sha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    publisher: Mapped[str] = mapped_column(String(300), default="")
    source_type: Mapped[str] = mapped_column(String(40), default="unknown")
    published_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), default="")
    credibility_score: Mapped[int] = mapped_column(Integer, default=0)
    credibility_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    injection_flags: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    claim_links: Mapped[list[ClaimSource]] = relationship(back_populates="source")


class ClaimSource(Base):
    __tablename__ = "claim_sources"
    __table_args__ = (UniqueConstraint("claim_id", "source_id", "relation", name="uq_claim_source_rel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    relation: Mapped[str] = mapped_column(String(20))
    quote: Mapped[str] = mapped_column(Text, default="")
    quote_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    claim: Mapped[Claim] = relationship(back_populates="sources")
    source: Mapped[Source] = relationship(back_populates="claim_links")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    claim_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    llm_provider: Mapped[str] = mapped_column(String(20), default="mock")
    model: Mapped[str] = mapped_column(String(60), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")

    article: Mapped[Article] = relationship(back_populates="runs")
    events: Mapped[list[AgentEvent]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AgentEvent.id"
    )


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    stage: Mapped[str] = mapped_column(String(30), default="")
    type: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(80), default="")
    claim_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    run: Mapped[AgentRun] = relationship(back_populates="events")


class EditorDecision(Base):
    __tablename__ = "editor_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    editor: Mapped[str] = mapped_column(String(120))
    override_verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    previous_verdict: Mapped[str] = mapped_column(String(20), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    claim: Mapped[Claim] = relationship(back_populates="decisions")
