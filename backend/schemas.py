"""Schematy Pydantic (wejście/wyjście REST oraz walidacja zapisu z MCP newsroom)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ArticleStatus = Literal["draft", "in_review", "verified"]
Verdict = Literal["potwierdzone", "wątpliwe", "fałszywe", "oczekuje"]
FinalVerdict = Literal["potwierdzone", "wątpliwe", "fałszywe"]
Category = Literal["liczbowe", "datowe", "cytat", "przyczynowe", "porównawcze", "inne"]
Relation = Literal["supports", "contradicts", "context"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Artykuły -----------------------------------------------------------
class ArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=100_000)
    author: str = Field(default="", max_length=120)


class ArticleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = Field(default=None, min_length=1, max_length=100_000)
    author: str | None = Field(default=None, max_length=120)
    status: ArticleStatus | None = None


class ArticleSummary(ORM):
    id: int
    title: str
    author: str
    status: str
    created_at: datetime
    claim_counts: dict[str, int] = Field(default_factory=dict)


class ArticleOut(ArticleSummary):
    body: str


# --- Źródła ------------------------------------------------------------
class SourceIn(BaseModel):
    url: str = Field(min_length=1, max_length=4000)
    final_url: str = ""
    title: str = ""
    publisher: str = ""
    source_type: str = "unknown"
    published_at: str | None = None
    fetched_at: datetime | None = None
    content_sha256: str = ""
    credibility_score: int = Field(default=0, ge=0, le=100)
    credibility_breakdown: dict[str, Any] = Field(default_factory=dict)
    injection_flags: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    is_primary: bool = False


class SourceOut(ORM):
    id: int
    url: str
    final_url: str
    title: str
    publisher: str
    source_type: str
    published_at: str | None
    fetched_at: datetime | None
    content_sha256: str
    credibility_score: int
    credibility_breakdown: dict[str, Any]
    injection_flags: list[dict[str, Any]]
    summary: str
    is_primary: bool


class ClaimSourceOut(ORM):
    id: int
    relation: str
    quote: str
    quote_verified: bool
    source: SourceOut


# --- Twierdzenia -------------------------------------------------------
class ClaimIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    category: Category = "inne"

    @field_validator("end_offset")
    @classmethod
    def _end_after_start(cls, v: int, info) -> int:
        start = info.data.get("start_offset")
        if start is not None and v <= start:
            raise ValueError("end_offset musi być większy od start_offset")
        return v


class ClaimUpdate(BaseModel):
    text: str | None = None
    category: Category | None = None


class EditorDecisionIn(BaseModel):
    editor: str = Field(min_length=1, max_length=120)
    override_verdict: FinalVerdict | None = None
    note: str = Field(default="", max_length=5000)


class EditorDecisionOut(ORM):
    id: int
    claim_id: int
    editor: str
    override_verdict: str | None
    previous_verdict: str
    note: str
    created_at: datetime


class ClaimOut(ORM):
    id: int
    article_id: int
    text: str
    start_offset: int
    end_offset: int
    category: str
    verdict: str
    effective_verdict: str
    confidence: float | None
    rationale: str
    checked_at: datetime | None
    verdict_details: dict[str, Any]
    sources: list[ClaimSourceOut] = Field(default_factory=list)
    decisions: list[EditorDecisionOut] = Field(default_factory=list)


class VerdictIn(BaseModel):
    verdict: FinalVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=8000)
    details: dict[str, Any] = Field(default_factory=dict)


class AttachSourceIn(BaseModel):
    source: SourceIn
    relation: Relation
    quote: str = Field(default="", max_length=4000)
    quote_verified: bool = False


# --- Audyt -------------------------------------------------------------
class AgentEventIn(BaseModel):
    stage: str = Field(default="", max_length=30)
    type: str = Field(min_length=1, max_length=30)
    name: str = Field(default="", max_length=80)
    claim_id: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class AgentEventOut(ORM):
    id: int
    run_id: str
    ts: datetime
    stage: str
    type: str
    name: str
    claim_id: int | None
    payload: dict[str, Any]
    duration_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class AgentRunOut(ORM):
    id: str
    article_id: int
    claim_id: int | None
    status: str
    llm_provider: str
    model: str
    started_at: datetime
    finished_at: datetime | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tool_calls: int
    progress: dict[str, Any]
    error: str


class VerifyRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=128)
