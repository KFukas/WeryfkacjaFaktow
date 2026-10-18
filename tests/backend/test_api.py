"""Testy REST API: CRUD artykułów, twierdzeń, źródeł, decyzji redaktora, raporty."""

from __future__ import annotations

from backend import schemas, services


def _article(client, body="Polska przystąpiła do Unii Europejskiej 1 maja 2004 r. Inne zdanie."):
    r = client.post("/api/articles", json={"title": "Test", "body": body, "author": "Autor"})
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_article_crud(client):
    art = _article(client)
    assert art["status"] == "draft"
    assert client.get(f"/api/articles/{art['id']}").json()["title"] == "Test"
    r = client.patch(f"/api/articles/{art['id']}", json={"title": "Nowy", "status": "verified"})
    assert r.json()["title"] == "Nowy" and r.json()["status"] == "verified"
    assert len(client.get("/api/articles").json()) == 1
    assert client.delete(f"/api/articles/{art['id']}").status_code == 204
    assert client.get(f"/api/articles/{art['id']}").status_code == 404


def test_article_validation(client):
    assert client.post("/api/articles", json={"title": "", "body": "x"}).status_code == 422
    assert client.patch("/api/articles/1", json={"status": "opublikowany"}).status_code in (404, 422)


def test_claims_offsets_validated_and_corrected(client):
    art = _article(client)
    body = "Polska przystąpiła do Unii Europejskiej 1 maja 2004 r."
    # błędne offsety, ale tekst występuje dokładnie raz → korekta
    r = client.post(f"/api/articles/{art['id']}/claims",
                    json=[{"text": body, "start_offset": 5, "end_offset": 10, "category": "datowe"}])
    assert r.status_code == 201, r.text
    claim = r.json()[0]
    assert (claim["start_offset"], claim["end_offset"]) == (0, len(body))
    assert claim["verdict"] == "oczekuje"
    # tekst spoza artykułu → 422
    r = client.post(f"/api/articles/{art['id']}/claims",
                    json=[{"text": "Zmyślone zdanie", "start_offset": 0, "end_offset": 15}])
    assert r.status_code == 422
    # idempotencja: ponowny zapis nie tworzy duplikatu
    client.post(f"/api/articles/{art['id']}/claims",
                json=[{"text": body, "start_offset": 0, "end_offset": len(body), "category": "datowe"}])
    assert len(client.get(f"/api/articles/{art['id']}/claims").json()) == 1
    # artykuł przeszedł do recenzji
    assert client.get(f"/api/articles/{art['id']}").json()["status"] == "in_review"


def test_end_offset_must_follow_start(client):
    art = _article(client)
    r = client.post(f"/api/articles/{art['id']}/claims", json=[{"text": "x", "start_offset": 5, "end_offset": 5}])
    assert r.status_code == 422


def test_verdict_requires_matching_source(db):
    art = services.create_article(db, schemas.ArticleCreate(title="T", body="Do NATO Polska wstąpiła w 2001 roku."))
    claim = services.save_claims(db, art.id, [schemas.ClaimIn(text=art.body, start_offset=0,
                                                               end_offset=len(art.body))])[0]
    import pytest

    with pytest.raises(services.DomainError):
        services.save_verdict(db, claim.id, schemas.VerdictIn(verdict="fałszywe", confidence=0.9, rationale="x"))
    services.attach_source(db, claim.id, schemas.AttachSourceIn(
        source=schemas.SourceIn(url="https://www.gov.pl/nato", credibility_score=80),
        relation="contradicts", quote="12 marca 1999 r.", quote_verified=True))
    with pytest.raises(services.DomainError):  # przeczące źródło nie wystarcza do „potwierdzone”
        services.save_verdict(db, claim.id, schemas.VerdictIn(verdict="potwierdzone", confidence=0.9, rationale="x"))
    out = services.save_verdict(db, claim.id, schemas.VerdictIn(verdict="fałszywe", confidence=0.9, rationale="x"))
    assert out.verdict == "fałszywe" and out.checked_at is not None
    # pewność spoza zakresu odrzucana przez schemat
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        schemas.VerdictIn(verdict="fałszywe", confidence=1.5, rationale="x")
    with pytest.raises(ValidationError):
        schemas.VerdictIn(verdict="prawda", confidence=0.5, rationale="x")


def test_editor_override_and_history(client, db):
    art = _article(client)
    body = "Polska przystąpiła do Unii Europejskiej 1 maja 2004 r."
    claim = client.post(f"/api/articles/{art['id']}/claims",
                        json=[{"text": body, "start_offset": 0, "end_offset": len(body)}]).json()[0]
    r = client.post(f"/api/claims/{claim['id']}/decisions",
                    json={"editor": "red. Nowak", "override_verdict": "potwierdzone", "note": "Sprawdzone ręcznie"})
    assert r.status_code == 201
    client.post(f"/api/claims/{claim['id']}/decisions",
                json={"editor": "red. Kowalska", "override_verdict": "wątpliwe", "note": "Do ponownej oceny"})
    got = client.get(f"/api/claims/{claim['id']}").json()
    assert got["verdict"] == "oczekuje"  # werdykt agenta bez zmian
    assert got["effective_verdict"] == "wątpliwe"  # redaktor ma ostatnie słowo
    history = client.get(f"/api/claims/{claim['id']}/decisions").json()
    assert [d["previous_verdict"] for d in history] == ["oczekuje", "potwierdzone"]
    assert client.post(f"/api/claims/{claim['id']}/decisions",
                       json={"editor": "x", "override_verdict": "oczekuje"}).status_code == 422


def test_report_export(client, db):
    art = _article(client)
    body = "Polska przystąpiła do Unii Europejskiej 1 maja 2004 r."
    claim = client.post(f"/api/articles/{art['id']}/claims",
                        json=[{"text": body, "start_offset": 0, "end_offset": len(body)}]).json()[0]
    services.attach_source(db, claim["id"], schemas.AttachSourceIn(
        source=schemas.SourceIn(url="https://www.gov.pl/ue", title="Polska w UE", credibility_score=80,
                                injection_flags=[{"type": "hidden_text", "severity": "high"}]),
        relation="supports", quote="od 1 maja 2004 r.", quote_verified=True))
    md = client.get(f"/api/articles/{art['id']}/report?format=md")
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert "Raport weryfikacji" in md.text and "hidden_text" in md.text
    js = client.get(f"/api/articles/{art['id']}/report?format=json").json()
    assert js["claims"][0]["sources"][0]["credibility_score"] == 80


def test_sources_endpoints(client, db):
    art = _article(client)
    body = "Polska przystąpiła do Unii Europejskiej 1 maja 2004 r."
    claim = client.post(f"/api/articles/{art['id']}/claims",
                        json=[{"text": body, "start_offset": 0, "end_offset": len(body)}]).json()[0]
    services.attach_source(db, claim["id"], schemas.AttachSourceIn(
        source=schemas.SourceIn(url="https://example.org/a", content_sha256="abc"), relation="context"))
    sources = client.get("/api/sources").json()
    assert len(sources) == 1
    assert client.get(f"/api/sources/{sources[0]['id']}").json()["url"] == "https://example.org/a"
    assert client.get("/api/sources/999").status_code == 404


def test_body_change_clears_claims(client):
    art = _article(client)
    body = "Polska przystąpiła do Unii Europejskiej 1 maja 2004 r."
    client.post(f"/api/articles/{art['id']}/claims", json=[{"text": body, "start_offset": 0, "end_offset": len(body)}])
    client.patch(f"/api/articles/{art['id']}", json={"body": "Zupełnie nowa treść."})
    assert client.get(f"/api/articles/{art['id']}/claims").json() == []


def test_seed_is_idempotent(seeded, client):
    from backend.seed import ARTICLES, seed

    assert seed() == 0
    arts = client.get("/api/articles").json()
    assert len(arts) == len(ARTICLES) >= 3


def test_migrations_match_models(tmp_path):
    """Migracja Alembic tworzy ten sam schemat co modele (brak dryfu)."""
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from alembic import command

    url = f"sqlite:///{(tmp_path / 'mig.db').as_posix()}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"articles", "claims", "sources", "claim_sources", "agent_runs", "agent_events",
            "editor_decisions"} <= tables
    command.check(cfg)  # rzuca, jeśli modele i migracje się rozjechały
