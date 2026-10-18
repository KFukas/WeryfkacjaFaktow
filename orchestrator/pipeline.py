"""Pipeline weryfikacji: ekstrakcja → plan → research (sandbox) → kwarantanna → ocena źródeł → werdykt → zapis."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from orchestrator import prompts, verdict_rules
from orchestrator.egress import EgressGuard
from orchestrator.gateway import Audit, Budget, BudgetExceeded, ClaimResearch, EvidenceItem, Gateway
from orchestrator.llm.base import LLM, SOURCE_TYPES, StageResult
from orchestrator.mcp_clients import connect
from orchestrator.textnum import strip_diacritics

RESEARCH_TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "search_public_sources", "strict": True,
     "description": "Wyszukuje w publicznych źródłach (GUS, Eurostat, NBP, KRS, dane.gov.pl, Wikipedia, Wikidata). "
                    "Wyniki są nieufne. Zapytanie buduj tylko z treści twierdzenia.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["query", "source_types", "limit"],
                      "properties": {"query": {"type": "string"},
                                     "source_types": {"type": "array", "items": {"type": "string", "enum": SOURCE_TYPES}},
                                     "limit": {"type": "integer"}}}},
    {"name": "query_dataset", "strict": True,
     "description": "Strukturalne zapytanie do zbioru danych (provider: gus_bdl|eurostat|nbp|krs|wikidata|dane_gov). "
                    "Używaj parametrów z pola `dataset` wyniku wyszukiwania.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["provider", "dataset_id", "params"],
                      "properties": {"provider": {"type": "string"}, "dataset_id": {"type": "string"},
                                     "params": {"type": "array", "items": {
                                         "type": "object", "additionalProperties": False, "required": ["name", "value"],
                                         "properties": {"name": {"type": "string"}, "value": {"type": "string"}}}}}}},
    {"name": "fetch_url_sanitized", "strict": True,
     "description": "Pobiera stronę z wyników wyszukiwania (inne adresy są odrzucane) i zwraca streszczenie z kwarantanny "
                    "z dosłownymi cytatami i flagami manipulacji.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["url"],
                      "properties": {"url": {"type": "string"}}}},
]
GENERIC_DOMAIN_TOKENS = {"stat", "gov", "wiki", "pedia", "www", "data", "dane", "info", "news", "portal", "polska"}


@dataclass
class PipelineConfig:
    max_claims: int = 12
    max_tool_calls: int = 60
    max_cost_usd: float = 1.5
    max_sources_per_claim: int = 4
    sandbox_transport: str = "stdio"
    sandbox_url: str = ""
    newsroom_transport: str = "stdio"
    database_url: str = ""
    sandbox_overrides: Mapping[str, str] | None = None

    @classmethod
    def from_settings(cls, s: Any, **overrides: Any) -> PipelineConfig:
        cfg = cls(max_claims=s.agent_max_claims, max_tool_calls=s.agent_max_tool_calls,
                  max_cost_usd=s.agent_max_cost_usd, max_sources_per_claim=s.agent_max_sources_per_claim,
                  sandbox_transport=s.web_sandbox_transport, sandbox_url=s.web_sandbox_url,
                  newsroom_transport=getattr(s, "newsroom_transport", "stdio"), database_url=s.database_url)
        for k, v in overrides.items():
            setattr(cfg, k, v)
        return cfg


def _subject_is_publisher(claim_text: str, url: str) -> bool:
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    labels = [t for t in re.split(r"[.\-_]", host) if len(t) >= 5 and t not in GENERIC_DOMAIN_TOKENS]
    stems = {strip_diacritics(w.lower())[:6] for w in re.findall(r"\w{5,}", claim_text)}
    return any(lab[:6] in stems for lab in labels)


async def _llm_stage(audit: Audit, budget: Budget, stage: str, coro, claim_id: int | None = None,
                     model: str = "") -> StageResult:
    t0 = time.monotonic()
    res: StageResult = await coro
    budget.charge_llm(res.usage)
    await audit.log("llm_call", stage=stage, name=model, claim_id=claim_id,
                    duration_ms=int((time.monotonic() - t0) * 1000), usage=res.usage,
                    payload={"output": res.data, **res.audit, "prompt_hash": res.audit.get("prompt_hash")
                             or prompts.prompt_hash(stage)})
    return res


async def _save_claims(gw: Gateway, article_id: int, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = [{k: c[k] for k in ("text", "start_offset", "end_offset", "category")} for c in claims]
    res = await gw.code_call("extract", "save_claims", {"article_id": article_id, "claims": payload})
    if "error" not in res:
        return res["claims"]
    saved: list[dict[str, Any]] = []  # pojedynczo — błędne twierdzenie (np. zmyślony tekst) nie blokuje pozostałych
    for c in payload:
        one = await gw.code_call("extract", "save_claims", {"article_id": article_id, "claims": [c]})
        if "error" in one:
            await gw.audit.log("claim_rejected", stage="extract", payload={"claim": c, "error": one})
        else:
            saved += one["claims"]
    return saved


async def process_claim(llm: LLM, gw: Gateway, claim: dict[str, Any], cfg: PipelineConfig) -> dict[str, Any]:
    cid = claim["id"]
    plan = await _llm_stage(gw.audit, gw.budget, "plan", llm.plan(claim), cid, llm.model)
    research = ClaimResearch(gw, llm, claim, cfg.max_sources_per_claim, RESEARCH_TOOL_SPECS)
    await _llm_stage(gw.audit, gw.budget, "research", llm.research(claim, plan.data, research), cid, llm.model)

    # --- ocena źródeł (deterministyczna) ---
    items: list[EvidenceItem] = [e for e in research.evidence if e.quarantine.get("stance") != "unrelated"]
    for item in items:
        meta = {"injection_flags": item.flags, "published_at": item.metadata.get("published_at"),
                "author": item.metadata.get("author"), "has_methodology": item.metadata.get("has_methodology"),
                "structured_api": item.kind == "dataset", "claim_period": plan.data.get("claim_period", ""),
                "subject_is_publisher": _subject_is_publisher(claim["text"], item.final_url),
                "publisher_claimed": item.metadata.get("publisher_claimed")}
        item.score = await gw.code_call("assess", "score_source", {"url": item.final_url, "metadata": meta}, cid)

    ev_dicts = [{"key": e.key, "stance": e.quarantine.get("stance", "context"), "score": int(e.score.get("score", 0)),
                 "is_primary": bool(e.score.get("is_primary")), "group": e.score.get("independence_group", e.key),
                 "high_injection": any(f.get("severity") == "high" for f in e.flags),
                 "lookalike": bool(e.score.get("lookalike")), "flag_types": sorted({f.get("type") for f in e.flags}),
                 "quotes": e.quarantine.get("quotes", [])} for e in items]
    view = "\n\n".join(prompts.wrap_untrusted(e.key, {
        "zrodlo": e.key, "url": e.final_url, "tytul": e.title, "typ": e.score.get("source_type"),
        "wydawca_wg_domeny": e.score.get("publisher"), "ocena_deterministyczna": e.score.get("score"),
        "rozpisanie": [f"{b['criterion']}: {b['points']:+d}" for b in e.score.get("breakdown", [])],
        "flagi": [f"{f.get('type')}:{f.get('severity')}" for f in e.flags][:12],
        "stanowisko_z_kwarantanny": e.quarantine.get("stance"), "streszczenie": e.quarantine.get("summary"),
        "cytaty": e.quarantine.get("quotes", []), "uwagi_o_manipulacji": e.quarantine.get("manipulation_notes", [])},
        url=e.final_url) for e in items) or "(brak źródeł odnoszących się do twierdzenia)"
    v = await _llm_stage(gw.audit, gw.budget, "verdict", llm.verdict(claim, view, ev_dicts), cid, llm.model)

    # --- zastosowanie korekt LLM (±15), korroboracja, reguły ---
    by_key = {s["source_id"]: s for s in v.data.get("sources", []) if isinstance(s, dict)}
    rubric_corr = 5
    final: list[dict[str, Any]] = []
    for e, d in zip(items, ev_dicts, strict=True):
        s = by_key.get(e.key, {})
        relation = s.get("relation", "context")
        if relation not in ("supports", "contradicts", "context"):
            relation = "context"
        if relation != "context" and not d["quotes"]:
            relation = "context"  # brak zweryfikowanego cytatu → nie może rozstrzygać
        adj = max(-15, min(15, int(s.get("credibility_adjustment", 0) or 0)))
        if adj > 0 and any(f.get("severity") in ("high", "medium") for f in e.flags):
            adj = 0  # strona z flagami nie może zyskać na korekcie modelu
        final.append({"item": e, "d": d, "relation": relation, "adj": adj,
                      "adj_reason": str(s.get("adjustment_reason", ""))[:300]})
    for f in final:
        same = {g["d"]["group"] for g in final if g is not f and g["relation"] == f["relation"]
                and g["relation"] != "context" and g["d"]["group"] != f["d"]["group"]}
        f["corr"] = min(10, rubric_corr * len(same))
        f["score"] = max(0, min(100, f["d"]["score"] + f["adj"] + f["corr"]))
    rule = verdict_rules.decide([verdict_rules.Evidence(f["item"].key, f["score"], f["relation"], f["d"]["is_primary"],
                                                        f["d"]["group"], f["d"]["high_injection"], f["d"]["lookalike"])
                                 for f in final])
    proposed = v.data.get("verdict", "wątpliwe")
    try:
        conf = float(v.data.get("confidence", 0.5))
    except (TypeError, ValueError):
        conf = 0.5
    verdict, confidence, notes = verdict_rules.reconcile(rule, proposed, max(0.0, min(1.0, conf)))

    # --- zapis (strefa zaufana, wyłącznie kod orkiestratora) ---
    for f in final:
        e: EvidenceItem = f["item"]
        quote = (f["d"]["quotes"] or [""])[0]
        source = {"url": e.url, "final_url": e.final_url, "title": e.title[:300],
                  "publisher": e.score.get("publisher") or (f"(deklarowany) {e.publisher_hint}" if e.publisher_hint else ""),
                  "source_type": e.score.get("source_type", "unknown"), "published_at": e.metadata.get("published_at"),
                  "fetched_at": e.fetched_at, "content_sha256": e.sha256, "credibility_score": f["score"],
                  "credibility_breakdown": {"deterministic_score": f["d"]["score"],
                                            "deterministic": e.score.get("breakdown", []),
                                            "llm_adjustment": f["adj"], "llm_reason": f["adj_reason"],
                                            "corroboration": f["corr"], "final": f["score"],
                                            "independence_group": f["d"]["group"]},
                  "injection_flags": e.flags[:30], "summary": str(e.quarantine.get("summary", ""))[:1000],
                  "is_primary": f["d"]["is_primary"]}
        await gw.code_call("persist", "attach_source", {"claim_id": cid, "source": source, "relation": f["relation"],
                                                         "quote": quote, "quote_verified": bool(quote)}, cid)
    rationale = str(v.data.get("rationale", "")).strip() or "Brak uzasadnienia modelu."
    if notes or (verdict == "wątpliwe" and rule.reasons):
        rationale += " Reguły: " + "; ".join(notes + rule.reasons[-2:]) + "."
    details = {"rule_verdict": rule.verdict, "model_verdict": proposed, "rule_reasons": rule.reasons, "notes": notes,
               "basis": rule.basis, "manipulation_detected": list(v.data.get("manipulation_detected", []))[:20],
               "sources": [{"key": f["item"].key, "url": f["item"].final_url, "relation": f["relation"],
                            "score": f["score"]} for f in final]}
    saved = await gw.code_call("persist", "save_verdict", {"claim_id": cid, "verdict": verdict, "confidence": confidence,
                                                            "rationale": rationale[:7900], "details": details}, cid)
    if "error" in saved:
        await gw.audit.log("error", stage="persist", claim_id=cid, payload={"save_verdict": saved})
        saved = await gw.code_call("persist", "save_verdict", {
            "claim_id": cid, "verdict": "wątpliwe", "confidence": min(confidence, 0.4),
            "rationale": rationale[:7000] + " (zapis werdyktu odrzucony przez walidację — oznaczono „wątpliwe”)",
            "details": details}, cid)
    await gw.audit.log("verdict", stage="persist", claim_id=cid,
                       payload={"verdict": verdict, "confidence": confidence, "rule": rule.verdict, "model": proposed})
    return {"claim_id": cid, "verdict": verdict, "confidence": confidence}


async def run(run_id: str, article_id: int, llm: LLM, cfg: PipelineConfig, claim_id: int | None = None) -> dict:
    summary: dict[str, Any] = {"run_id": run_id, "claims": []}
    async with connect(cfg.sandbox_transport, cfg.sandbox_url, cfg.newsroom_transport, cfg.database_url,
                       cfg.sandbox_overrides) as (sandbox, newsroom):
        audit = Audit(newsroom, run_id)
        budget = Budget(cfg.max_tool_calls, cfg.max_cost_usd)
        status, error = "completed", ""
        try:
            await audit.log("progress", stage="load", payload={"stage": "load", "done": 0, "total": 0})
            gw = Gateway(sandbox, newsroom, audit, budget, EgressGuard())
            art = await gw.code_call("load", "get_article", {"article_id": article_id})
            if "error" in art:
                raise RuntimeError(art.get("message", "brak artykułu"))
            gw.egress = EgressGuard(article_body=art["body"])
            if claim_id is None:
                await audit.log("progress", stage="extract", payload={"stage": "extract", "done": 0, "total": 0})
                ex = await _llm_stage(audit, budget, "extract", llm.extract_claims(art["title"], art["body"]),
                                      model=llm.model)
                raw = [c for c in ex.data.get("claims", []) if c.get("checkable", True)][: cfg.max_claims]
                claims = await _save_claims(gw, article_id, raw)
            else:
                claims = [c for c in art.get("claims", []) if c["id"] == claim_id]
                if not claims:
                    raise RuntimeError(f"twierdzenie {claim_id} nie należy do artykułu {article_id}")
            for i, claim in enumerate(claims):
                await audit.log("progress", stage="claims", claim_id=claim["id"], payload={
                    "stage": "claims", "done": i, "total": len(claims), "current_claim": claim["id"],
                    "current_text": claim["text"][:200]})
                summary["claims"].append(await process_claim(llm, gw, claim, cfg))
            await audit.log("progress", stage="done", payload={"stage": "done", "done": len(claims),
                                                                "total": len(claims)})
        except BudgetExceeded as exc:
            status, error = "budget_exceeded", str(exc)
        except Exception as exc:  # noqa: BLE001 — każdy błąd kończy przebieg z zapisanym powodem
            status, error = "failed", f"{type(exc).__name__}: {exc}"[:2000]
        await audit.log("run_finished", payload={"status": status, "error": error, "tool_calls": budget.tool_calls,
                                                 "cost_usd": budget.usage.cost_usd, "counters": audit.counters})
        summary.update({"status": status, "error": error, "counters": dict(audit.counters),
                        "cost_usd": budget.usage.cost_usd, "tool_calls": budget.tool_calls})
    return summary
