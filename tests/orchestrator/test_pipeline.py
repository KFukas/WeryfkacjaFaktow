"""Pipeline end-to-end (offline): werdykty seedów, audyt, allowlisty, budżet, idempotencja, API + SSE."""

from __future__ import annotations

import time

from sqlalchemy import select

from backend import services
from backend.models import AgentEvent, Article
from orchestrator import runner
from orchestrator.egress import EgressGuard
from orchestrator.gateway import Audit, Budget, ClaimResearch, Gateway
from orchestrator.llm.mock import MockLLM
from orchestrator.mcp_clients import connect

INPROC = {"sandbox_transport": "inproc", "newsroom_transport": "inproc"}
EXPECTED = {
    "Według GUS stopa bezrobocia": "potwierdzone",
    "Średnioroczna inflacja": "potwierdzone",
    "Liczba ludności Polski": "fałszywe",
    "Wzrost cen był spowodowany": "wątpliwe",
    "Polska przystąpiła do Unii": "potwierdzone",
    "Do NATO Polska wstąpiła": "fałszywe",
    "Ludność całej Unii": "potwierdzone",
    "Najwyższym szczytem Polski": "potwierdzone",
    "Wisła ma długość": "wątpliwe",
    "Średni kurs euro": "potwierdzone",
    "Spółka Wodociągi": "wątpliwe",
    "Mikołaj Kopernik": "wątpliwe",
    "Maria Skłodowska-Curie": "fałszywe",
    "Jak powiedział nam prof.": "wątpliwe",
}


async def _run(article_id: int, claim_id=None, **kw):
    rid, _ = runner.create_run(article_id, claim_id, provider="mock")
    return rid, await runner.execute(rid, article_id, claim_id, provider="mock", **{**INPROC, **kw})


async def test_seed_articles_get_expected_verdicts(seeded, db):
    for art in db.scalars(select(Article)).all():
        _, summary = await _run(art.id)
        assert summary["status"] == "completed", summary
    db.expire_all()
    got = {c.text: c.verdict for a in db.scalars(select(Article)) for c in a.claims}
    for prefix, verdict in EXPECTED.items():
        match = [v for t, v in got.items() if t.startswith(prefix)]
        assert match == [verdict], (prefix, match)
    assert len(got) == len(EXPECTED)  # opinie/prognozy nie są twierdzeniami
    # werdykty rozstrzygające mają źródło z dosłownym cytatem i rozpisaną oceną
    for a in db.scalars(select(Article)):
        for c in a.claims:
            if c.verdict in ("potwierdzone", "fałszywe"):
                rel = "supports" if c.verdict == "potwierdzone" else "contradicts"
                links = [s for s in c.sources if s.relation == rel]
                assert links and all(s.quote_verified and s.quote for s in links)
                assert links[0].source.credibility_breakdown["deterministic"]
                assert 0 < c.confidence <= 1 and c.rationale
            assert a.status == "in_review"


async def test_audit_trail_complete(seeded, db):
    rid, summary = await _run(2)
    events = list(db.scalars(select(AgentEvent).where(AgentEvent.run_id == rid)))
    types = {e.type for e in events}
    assert {"progress", "llm_call", "tool_call", "verdict", "run_finished"} <= types
    llm = [e for e in events if e.type == "llm_call"]
    assert all(e.payload.get("prompt_hash") for e in llm)
    tool = [e for e in events if e.type == "tool_call"]
    assert {e.payload["server"] for e in tool} == {"web-sandbox", "newsroom"}
    assert all(e.payload["actor"] == "code" for e in tool if e.payload["server"] == "newsroom")
    run = services.get_run(db, rid)
    db.refresh(run)
    # run.tool_calls liczy wszystkie wywołania (audyt), budżet — tylko zewnętrzne (sandbox)
    assert run.status == "completed" and run.tool_calls >= summary["tool_calls"] > 0 and run.finished_at


async def test_reverify_single_claim_keeps_editor_decisions(seeded, db):
    from backend import schemas

    await _run(2)
    db.expire_all()
    art = db.get(Article, 2)
    claim = next(c for c in art.claims if c.text.startswith("Do NATO"))
    services.add_editor_decision(db, claim.id, schemas.EditorDecisionIn(editor="red. Test", override_verdict="wątpliwe",
                                                                      note="do sprawdzenia"))
    rid, summary = await _run(2, claim.id)
    assert summary["status"] == "completed" and len(summary["claims"]) == 1
    db.expire_all()
    claim = services.get_claim(db, claim.id)
    assert claim.verdict == "fałszywe" and claim.effective_verdict == "wątpliwe" and len(claim.decisions) == 1
    assert len(db.get(Article, 2).claims) == 3  # brak duplikatów


async def test_budget_limit_stops_run(seeded):
    _, summary = await _run(1, max_tool_calls=3)
    assert summary["status"] == "budget_exceeded"


def test_idempotent_run_creation(seeded):
    a, created_a = runner.create_run(1, idempotency_key="klucz-1", provider="mock")
    b, created_b = runner.create_run(1, idempotency_key="klucz-1", provider="mock")
    assert a == b and created_a and not created_b
    c, created_c = runner.create_run(1, provider="mock")  # trwający przebieg zwracany zamiast nowego
    assert c == a and not created_c


async def test_llm_cannot_call_write_tools_or_unlisted_urls(seeded, db):
    rid, _ = runner.create_run(2, provider="mock")
    async with connect("inproc", "", "inproc", "") as (sandbox, newsroom):
        gw = Gateway(sandbox, newsroom, Audit(newsroom, rid), Budget(50, 1.0),
                     EgressGuard(article_body="Tajne KANAREK-ABCDEF12"))
        claim = {"id": None, "text": "Do NATO Polska wstąpiła w 2001 roku.", "category": "datowe"}
        tools = ClaimResearch(gw, MockLLM(), claim, 4, [])
        for name in ("save_verdict", "attach_source", "log_agent_event", "get_article", "score_source"):
            out = await tools.call(name, {"claim_id": 1, "verdict": "potwierdzone"})
            assert out.is_error and out.data["error"] == "denied"
        out = await tools.call("fetch_url_sanitized", {"url": "https://evil.example/steal"})
        assert out.is_error  # URL spoza wyników wyszukiwania
        out = await tools.call("search_public_sources", {"query": "NATO KANAREK-ABCDEF12"})
        assert out.is_error  # kanarek nie wychodzi na zewnątrz
    events = list(db.scalars(select(AgentEvent).where(AgentEvent.run_id == rid)))
    types = [e.type for e in events]
    assert types.count("tool_violation") == 5 and "provenance_blocked" in types and "egress_blocked" in types
    assert not [e for e in events if e.type == "tool_call"]  # nic nie zostało wykonane


def test_api_verify_and_stream(seeded, client, monkeypatch):
    from backend.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "web_sandbox_transport", "inproc")
    monkeypatch.setattr(s, "newsroom_transport", "inproc")
    monkeypatch.setattr(s, "llm_provider", "mock")
    r = client.post("/api/articles/2/verify", json={"idempotency_key": "api-1"})
    assert r.status_code == 202
    run_id = r.json()["id"]
    assert client.post("/api/articles/2/verify", json={"idempotency_key": "api-1"}).json()["id"] == run_id
    with client.stream("GET", f"/api/runs/{run_id}/stream") as resp:
        body = "".join(resp.iter_text())
    assert "event: agent" in body and "event: end" in body
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "completed", run
    claims = client.get("/api/articles/2/claims").json()
    assert {c["verdict"] for c in claims} == {"potwierdzone", "fałszywe"}
    events = client.get(f"/api/runs/{run_id}/events").json()
    assert events and events[-1]["type"] == "run_finished"
    nato = next(c for c in claims if c["text"].startswith("Do NATO"))
    r = client.post(f"/api/claims/{nato['id']}/reverify")
    assert r.status_code == 202 and r.json()["claim_id"] == nato["id"]
    for _ in range(100):
        if client.get(f"/api/runs/{r.json()['id']}").json()["status"] != "running":
            break
        time.sleep(0.1)


async def test_stdio_transports_end_to_end(seeded, db_url, db):
    """Prawdziwe procesy potomne: sandbox (bez sekretów w środowisku) i newsroom (z DATABASE_URL)."""
    rid, summary = await _run(2, sandbox_transport="stdio", newsroom_transport="stdio", database_url=db_url)
    assert summary["status"] == "completed", summary
    db.expire_all()
    assert {c.verdict for c in db.get(Article, 2).claims} == {"potwierdzone", "fałszywe"}
