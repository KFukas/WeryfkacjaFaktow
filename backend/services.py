"""Operacje strefy zaufanej — wspólne dla REST API i serwera MCP „newsroom”.

Cała walidacja zapisu (schemat werdyktu, offsety twierdzeń, wymagane źródła) jest tutaj, żeby żadna ścieżka
(API, MCP, orkiestrator) nie mogła jej ominąć.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend import schemas
from backend.models import (
    AgentEvent,
    AgentRun,
    Article,
    Claim,
    ClaimSource,
    EditorDecision,
    Source,
    utcnow,
)


class DomainError(ValueError):
    """Naruszenie reguł domenowych (mapowane na HTTP 422 / błąd narzędzia MCP)."""


class NotFound(LookupError):
    pass


# --- Artykuły ----------------------------------------------------------
def get_article(db: Session, article_id: int) -> Article:
    art = db.get(Article, article_id)
    if art is None:
        raise NotFound(f"Artykuł {article_id} nie istnieje")
    return art


def claim_counts(article: Article) -> dict[str, int]:
    return dict(Counter(c.effective_verdict for c in article.claims))


def list_articles(db: Session, status: str | None = None) -> list[Article]:
    stmt = select(Article).options(selectinload(Article.claims).selectinload(Claim.decisions)).order_by(Article.id)
    if status:
        stmt = stmt.where(Article.status == status)
    return list(db.scalars(stmt))


def list_pending_articles(db: Session) -> list[Article]:
    stmt = select(Article).where(Article.status.in_(["draft", "in_review"])).order_by(Article.id)
    return list(db.scalars(stmt))


def create_article(db: Session, data: schemas.ArticleCreate) -> Article:
    art = Article(title=data.title, body=data.body, author=data.author)
    db.add(art)
    db.commit()
    db.refresh(art)
    return art


def update_article(db: Session, article_id: int, data: schemas.ArticleUpdate) -> Article:
    art = get_article(db, article_id)
    changes = data.model_dump(exclude_unset=True)
    if "body" in changes and changes["body"] != art.body and art.claims:
        # Offsety twierdzeń przestałyby pasować — zmiana treści czyści analizę.
        art.claims.clear()
        art.status = "draft"
    for k, v in changes.items():
        setattr(art, k, v)
    db.commit()
    db.refresh(art)
    return art


def delete_article(db: Session, article_id: int) -> None:
    db.delete(get_article(db, article_id))
    db.commit()


# --- Twierdzenia --------------------------------------------------------
def get_claim(db: Session, claim_id: int) -> Claim:
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise NotFound(f"Twierdzenie {claim_id} nie istnieje")
    return claim


def _resolve_offsets(body: str, c: schemas.ClaimIn) -> tuple[int, int]:
    """Weryfikuje offsety; jeżeli model się pomylił, a tekst występuje w artykule dokładnie raz — koryguje."""
    if 0 <= c.start_offset < c.end_offset <= len(body) and body[c.start_offset : c.end_offset] == c.text:
        return c.start_offset, c.end_offset
    first = body.find(c.text)
    if first == -1:
        raise DomainError(f"Tekst twierdzenia nie występuje w artykule: {c.text[:80]!r}")
    # przy wielu wystąpieniach wybieramy najbliższe podanemu offsetowi
    best, pos = first, first
    while pos != -1:
        if abs(pos - c.start_offset) < abs(best - c.start_offset):
            best = pos
        pos = body.find(c.text, pos + 1)
    return best, best + len(c.text)


def save_claims(db: Session, article_id: int, claims: list[schemas.ClaimIn]) -> list[Claim]:
    """Zapisuje twierdzenia idempotentnie: to samo (start, end) nie tworzy duplikatu."""
    art = get_article(db, article_id)
    existing = {(c.start_offset, c.end_offset): c for c in art.claims}
    result: list[Claim] = []
    for c in claims:
        start, end = _resolve_offsets(art.body, c)
        found = existing.get((start, end))
        if found is None:
            found = Claim(article_id=art.id, text=art.body[start:end], start_offset=start, end_offset=end,
                          category=c.category)
            db.add(found)
            existing[(start, end)] = found
        else:
            found.category = c.category
        result.append(found)
    if art.status == "draft":
        art.status = "in_review"
    db.commit()
    for r in result:
        db.refresh(r)
    return result


def update_claim(db: Session, claim_id: int, data: schemas.ClaimUpdate) -> Claim:
    claim = get_claim(db, claim_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(claim, k, v)
    db.commit()
    db.refresh(claim)
    return claim


def delete_claim(db: Session, claim_id: int) -> None:
    db.delete(get_claim(db, claim_id))
    db.commit()


def reset_claim(db: Session, claim_id: int) -> Claim:
    """Przygotowuje twierdzenie do ponownej weryfikacji (źródła agenta usuwane, decyzje redaktora zostają)."""
    claim = get_claim(db, claim_id)
    for link in list(claim.sources):
        db.delete(link)
    claim.verdict, claim.confidence, claim.rationale, claim.checked_at = "oczekuje", None, "", None
    claim.verdict_details = {}
    db.commit()
    db.refresh(claim)
    return claim


# --- Źródła -------------------------------------------------------------
def upsert_source(db: Session, data: schemas.SourceIn) -> Source:
    stmt = select(Source).where(Source.url == data.url, Source.content_sha256 == data.content_sha256)
    src = db.scalars(stmt).first()
    values = data.model_dump()
    if src is None:
        src = Source(**values)
        db.add(src)
    else:
        for k, v in values.items():
            setattr(src, k, v)
    db.flush()
    return src


def attach_source(db: Session, claim_id: int, data: schemas.AttachSourceIn) -> ClaimSource:
    claim = get_claim(db, claim_id)
    src = upsert_source(db, data.source)
    link = next((s for s in claim.sources if s.source_id == src.id and s.relation == data.relation), None)
    if link is None:
        link = ClaimSource(source=src, relation=data.relation)
        claim.sources.append(link)
    link.quote = data.quote
    link.quote_verified = data.quote_verified
    db.commit()
    db.refresh(link)
    return link


def list_sources(db: Session) -> list[Source]:
    return list(db.scalars(select(Source).order_by(Source.id)))


def get_source(db: Session, source_id: int) -> Source:
    src = db.get(Source, source_id)
    if src is None:
        raise NotFound(f"Źródło {source_id} nie istnieje")
    return src


# --- Werdykty -----------------------------------------------------------
def save_verdict(db: Session, claim_id: int, data: schemas.VerdictIn) -> Claim:
    """Zapis werdyktu z walidacją: potwierdzone wymaga źródła wspierającego, fałszywe — przeczącego."""
    claim = get_claim(db, claim_id)
    relations = {link.relation for link in claim.sources}
    if data.verdict == "potwierdzone" and "supports" not in relations:
        raise DomainError("Werdykt „potwierdzone” wymaga co najmniej jednego źródła wspierającego")
    if data.verdict == "fałszywe" and "contradicts" not in relations:
        raise DomainError("Werdykt „fałszywe” wymaga co najmniej jednego źródła przeczącego")
    claim.verdict = data.verdict
    claim.confidence = round(data.confidence, 3)
    claim.rationale = data.rationale
    claim.verdict_details = data.details
    claim.checked_at = utcnow()
    db.commit()
    db.refresh(claim)
    return claim


def add_editor_decision(db: Session, claim_id: int, data: schemas.EditorDecisionIn) -> EditorDecision:
    claim = get_claim(db, claim_id)
    decision = EditorDecision(
        claim_id=claim.id,
        editor=data.editor,
        override_verdict=data.override_verdict,
        previous_verdict=claim.effective_verdict,
        note=data.note,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


# --- Audyt agenta ------------------------------------------------------
def get_run(db: Session, run_id: str) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise NotFound(f"Przebieg {run_id} nie istnieje")
    return run


def log_agent_event(db: Session, run_id: str, event: schemas.AgentEventIn) -> AgentEvent:
    run = get_run(db, run_id)
    ev = AgentEvent(run_id=run.id, **event.model_dump())
    db.add(ev)
    run.input_tokens += event.input_tokens
    run.output_tokens += event.output_tokens
    run.cost_usd = round(run.cost_usd + event.cost_usd, 6)
    if event.type == "tool_call":
        run.tool_calls += 1
    if event.type == "progress":
        run.progress = dict(event.payload)
        if run.status == "queued":
            run.status = "running"
    if event.type == "run_finished":
        run.status = str(event.payload.get("status", "completed"))
        run.error = str(event.payload.get("error", ""))[:4000]
        run.finished_at = utcnow()
    db.commit()
    db.refresh(ev)
    return ev


def create_run(db: Session, article_id: int, claim_id: int | None, provider: str, model: str,
               idempotency_key: str | None = None) -> tuple[AgentRun, bool]:
    """Tworzy przebieg albo zwraca istniejący (ten sam klucz idempotencji lub trwający przebieg). → (run, created)"""
    get_article(db, article_id)
    if idempotency_key:
        existing = db.scalars(select(AgentRun).where(AgentRun.idempotency_key == idempotency_key)).first()
        if existing is not None:
            return existing, False
    active = db.scalars(select(AgentRun).where(AgentRun.article_id == article_id,
                                              AgentRun.claim_id.is_(claim_id) if claim_id is None
                                              else AgentRun.claim_id == claim_id,
                                              AgentRun.status.in_(["queued", "running"]))).first()
    if active is not None:
        return active, False
    run = AgentRun(article_id=article_id, claim_id=claim_id, llm_provider=provider, model=model,
                   idempotency_key=idempotency_key, progress={"stage": "queued"})
    db.add(run)
    db.commit()
    db.refresh(run)
    return run, True


# --- Raport -------------------------------------------------------------
VERDICT_ICON = {"potwierdzone": "✔", "wątpliwe": "?", "fałszywe": "✘", "oczekuje": "…"}


def report_json(article: Article) -> dict[str, Any]:
    return {
        "article": {"id": article.id, "title": article.title, "author": article.author, "status": article.status},
        "summary": claim_counts(article),
        "claims": [
            {
                "id": c.id,
                "text": c.text,
                "offsets": [c.start_offset, c.end_offset],
                "category": c.category,
                "agent_verdict": c.verdict,
                "final_verdict": c.effective_verdict,
                "confidence": c.confidence,
                "rationale": c.rationale,
                "editor_decisions": [
                    {"editor": d.editor, "override_verdict": d.override_verdict, "note": d.note,
                     "created_at": d.created_at.isoformat()}
                    for d in c.decisions
                ],
                "sources": [
                    {
                        "url": link.source.final_url or link.source.url,
                        "title": link.source.title,
                        "publisher": link.source.publisher,
                        "relation": link.relation,
                        "quote": link.quote,
                        "credibility_score": link.source.credibility_score,
                        "injection_flags": [f.get("type") for f in link.source.injection_flags],
                    }
                    for link in c.sources
                ],
            }
            for c in article.claims
        ],
    }


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def report_markdown(article: Article) -> str:
    data = report_json(article)
    lines = [
        f"# Raport weryfikacji: {article.title}",
        "",
        f"- Autor: {article.author or '—'}",
        f"- Status: {article.status}",
        "- Podsumowanie: " + (", ".join(f"{k}: {v}" for k, v in data["summary"].items()) or "brak twierdzeń"),
        "",
        "| # | Twierdzenie | Werdykt | Pewność |",
        "|---|---|---|---|",
    ]
    for i, c in enumerate(data["claims"], 1):
        conf = f"{c['confidence']:.2f}" if c["confidence"] is not None else "—"
        verdict = f"{VERDICT_ICON.get(c['final_verdict'], '')} {c['final_verdict']}"
        lines.append(f"| {i} | {_md_escape(c['text'])} | {verdict} | {conf} |")
    for i, c in enumerate(data["claims"], 1):
        lines += ["", f"## {i}. {c['text']}", "", f"**Werdykt:** {c['final_verdict']}"]
        if c["final_verdict"] != c["agent_verdict"]:
            lines.append(f"(agent: {c['agent_verdict']}; nadpisane przez redaktora)")
        if c["rationale"]:
            lines += ["", f"**Uzasadnienie:** {c['rationale']}"]
        if c["sources"]:
            lines += ["", "**Źródła:**"]
            for s in c["sources"]:
                flags = f" ⚠ flagi: {', '.join(s['injection_flags'])}" if s["injection_flags"] else ""
                lines.append(f"- [{s['relation']}] {s['title'] or s['url']} — {s['url']} "
                             f"(wiarygodność {s['credibility_score']}/100){flags}")
                if s["quote"]:
                    lines.append(f"  > {_md_escape(s['quote'])}")
        for d in c["editor_decisions"]:
            lines.append(f"- Decyzja redaktora {d['editor']}: {d['override_verdict'] or 'bez zmiany'} — {d['note']}")
    return "\n".join(lines) + "\n"
