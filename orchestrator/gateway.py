"""Bramka narzędzi: allowlisty per etap, pochodzenie URL-i, strażnik ruchu wychodzącego, budżet, audyt.

Dwóch „aktorów”:
* `llm`  — wywołania zlecone przez model; dozwolone WYŁĄCZNIE narzędzia odczytu strefy nieufnej w etapie research;
* `code` — wywołania orkiestratora (np. zapis werdyktu po walidacji regułami).
Każda próba spoza allowlisty jest odrzucana i zapisywana jako `tool_violation` (nie jest wykonywana).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from orchestrator.egress import EgressGuard
from orchestrator.llm.base import Usage
from orchestrator.mcp_clients import McpTools
from orchestrator.prompts import prompt_hash, wrap_untrusted

SANDBOX_TOOLS = {"search_public_sources", "query_dataset", "fetch_url_sanitized", "score_source"}
NEWSROOM_TOOLS = {"get_article", "list_pending_articles", "save_claims", "attach_source", "save_verdict",
                  "log_agent_event"}

LLM_ALLOWLIST: dict[str, set[str]] = {
    "extract": set(),
    "plan": set(),
    "research": {"search_public_sources", "query_dataset", "fetch_url_sanitized"},
    "quarantine": set(),
    "assess": set(),
    "verdict": set(),
}
CODE_ALLOWLIST: dict[str, set[str]] = {
    "load": {"get_article"},
    "extract": {"save_claims"},
    "assess": {"score_source"},
    "persist": {"attach_source", "save_verdict"},
}
MAX_FETCHES_PER_CLAIM = 4


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    max_tool_calls: int
    max_cost_usd: float
    tool_calls: int = 0
    usage: Usage = field(default_factory=Usage)

    def charge_tool(self) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.max_tool_calls:
            raise BudgetExceeded(f"przekroczono limit {self.max_tool_calls} wywołań narzędzi")

    def charge_llm(self, usage: Usage) -> None:
        self.usage.add(usage)
        if self.usage.cost_usd > self.max_cost_usd:
            raise BudgetExceeded(f"przekroczono limit kosztu {self.max_cost_usd} USD")


@dataclass
class Audit:
    newsroom: McpTools
    run_id: str
    counters: dict[str, int] = field(default_factory=dict)

    async def log(self, type_: str, *, stage: str = "", name: str = "", claim_id: int | None = None,
                  payload: dict[str, Any] | None = None, duration_ms: int = 0, usage: Usage | None = None) -> None:
        self.counters[type_] = self.counters.get(type_, 0) + 1
        u = usage or Usage()
        event = {"stage": stage, "type": type_, "name": name[:80], "claim_id": claim_id,
                 "payload": _clip(payload or {}), "duration_ms": duration_ms, "input_tokens": u.input_tokens,
                 "output_tokens": u.output_tokens, "cost_usd": u.cost_usd}
        await self.newsroom.call("log_agent_event", {"run_id": self.run_id, "event": event})


def _clip(obj: Any, limit: int = 20_000) -> Any:
    text = json.dumps(obj, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return json.loads(text)
    return {"truncated": True, "preview": text[:limit]}


@dataclass
class ToolOutcome:
    data: dict[str, Any]
    view: str
    is_error: bool = False


class Gateway:
    def __init__(self, sandbox: McpTools, newsroom: McpTools, audit: Audit, budget: Budget, egress: EgressGuard):
        self.sandbox, self.newsroom, self.audit, self.budget, self.egress = sandbox, newsroom, audit, budget, egress

    async def _execute(self, stage: str, tool: str, args: dict[str, Any], actor: str, claim_id: int | None) -> dict:
        server = self.sandbox if tool in SANDBOX_TOOLS else self.newsroom
        if server is self.sandbox:
            self.budget.charge_tool()
        t0 = time.monotonic()
        result = await server.call(tool, args)
        ms = int((time.monotonic() - t0) * 1000)
        await self.audit.log("tool_call", stage=stage, name=tool, claim_id=claim_id, duration_ms=ms,
                             payload={"actor": actor, "server": server.name, "args": args,
                                      "result_summary": _summarize(tool, result)})
        return result

    async def code_call(self, stage: str, tool: str, args: dict[str, Any], claim_id: int | None = None) -> dict:
        if tool not in CODE_ALLOWLIST.get(stage, set()):
            await self.audit.log("tool_violation", stage=stage, name=tool, claim_id=claim_id,
                                 payload={"actor": "code", "reason": "narzędzie spoza allowlisty etapu"})
            raise PermissionError(f"etap {stage}: narzędzie {tool} niedozwolone")
        return await self._execute(stage, tool, args, "code", claim_id)

    async def deny(self, stage: str, tool: str, args: dict[str, Any], reason: str, claim_id: int | None,
                   type_: str = "tool_violation") -> ToolOutcome:
        await self.audit.log(type_, stage=stage, name=tool, claim_id=claim_id,
                             payload={"actor": "llm", "reason": reason, "args": args})
        data = {"error": "denied", "message": reason}
        return ToolOutcome(data, json.dumps(data, ensure_ascii=False), is_error=True)


def _summarize(tool: str, result: dict) -> dict:
    if "error" in result:
        return {"error": result.get("error"), "message": str(result.get("message", ""))[:200]}
    if tool == "search_public_sources":
        return {"results": [r.get("url") for r in result.get("results", [])][:10]}
    if tool == "fetch_url_sanitized":
        return {"final_url": result.get("final_url"), "sha256": result.get("content_sha256"),
                "chars": len(result.get("text", "")), "flags": [f.get("type") for f in result.get("injection_flags", [])],
                "removed": result.get("removed")}
    if tool == "score_source":
        return {"score": result.get("score"), "type": result.get("source_type"), "lookalike": result.get("lookalike")}
    if tool == "query_dataset":
        return {"provider": result.get("provider"), "dataset_id": result.get("dataset_id"),
                "url": (result.get("metadata") or {}).get("url")}
    return {k: result.get(k) for k in list(result)[:6]}


@dataclass
class EvidenceItem:
    key: str
    kind: str  # page | dataset
    url: str
    final_url: str
    title: str
    text: str
    publisher_hint: str
    metadata: dict[str, Any]
    flags: list[dict[str, Any]]
    sha256: str
    fetched_at: str | None
    quarantine: dict[str, Any] = field(default_factory=dict)
    score: dict[str, Any] = field(default_factory=dict)


class ClaimResearch:
    """Narzędzia etapu research dla jednego twierdzenia (implementuje protokół ResearchTools)."""

    def __init__(self, gateway: Gateway, llm, claim: dict[str, Any], max_sources: int, tool_specs: list[dict]):
        self.g, self.llm, self.claim = gateway, llm, claim
        self.max_sources = max_sources
        self.allowed_urls: dict[str, dict[str, Any]] = {}  # URL z wyników wyszukiwania → metadane wyniku
        self.evidence: list[EvidenceItem] = []
        self.fetches = 0
        self._tool_specs = tool_specs

    def tool_definitions(self) -> list[dict[str, Any]]:
        return self._tool_specs

    @property
    def claim_id(self) -> int | None:
        return self.claim.get("id")

    async def call(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        stage = "research"
        if name not in LLM_ALLOWLIST[stage]:
            return await self.g.deny(stage, name, args, f"narzędzie {name} nie jest dostępne w etapie research",
                                     self.claim_id)
        handler = {"search_public_sources": self._search, "query_dataset": self._dataset,
                   "fetch_url_sanitized": self._fetch}[name]
        return await handler(dict(args))

    async def _search(self, args: dict[str, Any]) -> ToolOutcome:
        query = str(args.get("query", ""))[:300]
        reason = self.g.egress.check_text(query, allowed_context=self.claim["text"])
        if reason:
            return await self.g.deny("research", "search_public_sources", {"query": query[:120]}, reason,
                                     self.claim_id, type_="egress_blocked")
        call_args = {"query": query, "limit": int(args.get("limit", 6) or 6)}
        if args.get("source_types"):
            call_args["source_types"] = list(args["source_types"])[:8]
        result = await self.g._execute("research", "search_public_sources", call_args, "llm", self.claim_id)
        view_items = []
        for i, r in enumerate(result.get("results", []), 1):
            self.allowed_urls[r["url"]] = r
            item = {"n": i, "provider": r.get("provider"), "title": r.get("title"), "url": r.get("url"),
                    "snippet": r.get("snippet"), "flags": [f.get("type") for f in r.get("snippet_flags", [])]}
            if r.get("dataset"):
                item["dataset"] = r["dataset"]
            view_items.append(item)
        view = wrap_untrusted("wyniki-wyszukiwania", {"results": view_items, "errors": result.get("errors", [])})
        return ToolOutcome(result, view, "error" in result)

    async def _dataset(self, args: dict[str, Any]) -> ToolOutcome:
        provider, dataset_id = str(args.get("provider", "")), str(args.get("dataset_id", ""))
        params = args.get("params") or {}
        if isinstance(params, list):  # format ze schematu strict: [{"name":…, "value":…}]
            params = {str(p.get("name")): str(p.get("value")) for p in params if isinstance(p, dict)}
        reason = self.g.egress.check_text(json.dumps([provider, dataset_id, params], ensure_ascii=False),
                                          allowed_context=self.claim["text"])
        if reason:
            return await self.g.deny("research", "query_dataset", args, reason, self.claim_id, type_="egress_blocked")
        if len(self.evidence) >= self.max_sources:
            return await self.g.deny("research", "query_dataset", args, "osiągnięto limit źródeł dla twierdzenia",
                                     self.claim_id, type_="limit")
        result = await self.g._execute("research", "query_dataset",
                                       {"provider": provider, "dataset_id": dataset_id, "params": params}, "llm",
                                       self.claim_id)
        if "error" in result:
            return ToolOutcome(result, json.dumps(result, ensure_ascii=False), True)
        meta = result.get("metadata") or {}
        url = meta.get("url") or f"dataset://{provider}/{dataset_id}"
        item = EvidenceItem(key=f"S{len(self.evidence) + 1}", kind="dataset", url=url, final_url=url,
                            title=meta.get("title", dataset_id), text=result.get("text", ""),
                            publisher_hint=meta.get("publisher", ""), metadata={**meta, "structured_api": True},
                            flags=result.get("injection_flags", []), sha256="", fetched_at=None)
        return await self._quarantine_and_view(item)

    async def _fetch(self, args: dict[str, Any]) -> ToolOutcome:
        url = str(args.get("url", ""))
        if url not in self.allowed_urls:
            return await self.g.deny("research", "fetch_url_sanitized", {"url": url[:300]},
                                     "URL nie pochodzi z wyników wyszukiwania (zasada pochodzenia)", self.claim_id,
                                     type_="provenance_blocked")
        reason = self.g.egress.check_url(url, allowed_context=self.claim["text"])
        if reason:
            return await self.g.deny("research", "fetch_url_sanitized", {"url": url[:300]}, reason, self.claim_id,
                                     type_="egress_blocked")
        if self.fetches >= MAX_FETCHES_PER_CLAIM or len(self.evidence) >= self.max_sources:
            return await self.g.deny("research", "fetch_url_sanitized", {"url": url}, "osiągnięto limit pobrań",
                                     self.claim_id, type_="limit")
        self.fetches += 1
        env = await self.g._execute("research", "fetch_url_sanitized", {"url": url}, "llm", self.claim_id)
        if "error" in env:
            return ToolOutcome(env, json.dumps(env, ensure_ascii=False), True)
        hit = self.allowed_urls.get(url, {})
        item = EvidenceItem(key=f"S{len(self.evidence) + 1}", kind="page", url=url, final_url=env.get("final_url", url),
                            title=env.get("title", ""), text=env.get("text", ""),
                            publisher_hint=hit.get("publisher", ""), metadata=env.get("metadata", {}),
                            flags=env.get("injection_flags", []), sha256=env.get("content_sha256", ""),
                            fetched_at=env.get("fetched_at"))
        high = [f for f in item.flags if f.get("severity") == "high"]
        if high:
            await self.g.audit.log("injection_detected", stage="research", name="fetch_url_sanitized",
                                   claim_id=self.claim_id, payload={"url": url, "flags": item.flags[:10]})
        return await self._quarantine_and_view(item)

    async def _quarantine_and_view(self, item: EvidenceItem) -> ToolOutcome:
        wrapped = wrap_untrusted(item.key, item.text, url=item.final_url, sha=item.sha256)
        t0 = time.monotonic()
        q = await self.llm.quarantine(self.claim, item.key, wrapped, item.text)
        self.g.budget.charge_llm(q.usage)
        data = q.data
        verified, rejected = verify_quotes(data.get("quotes", []), item.text)
        data = {**data, "quotes": verified}
        item.quarantine = data
        self.evidence.append(item)
        await self.g.audit.log("llm_call", stage="quarantine", name=self.llm.model, claim_id=self.claim_id,
                               duration_ms=int((time.monotonic() - t0) * 1000), usage=q.usage,
                               payload={"source": item.key, "url": item.final_url, "output": data,
                                        "rejected_quotes": rejected, "prompt_hash": prompt_hash("quarantine"),
                                        **q.audit})
        if rejected:
            await self.g.audit.log("quote_rejected", stage="quarantine", claim_id=self.claim_id,
                                   payload={"source": item.key, "quotes": rejected})
        view = wrap_untrusted(item.key, {"source": item.key, "url": item.final_url, "title": item.title,
                                         "stance": data.get("stance"), "summary": data.get("summary"),
                                         "quotes": verified, "manipulation_notes": data.get("manipulation_notes", []),
                                         "flags": [f"{f.get('type')}:{f.get('severity')}" for f in item.flags]})
        return ToolOutcome({"source": item.key, **data}, view)


def _ws(s: str) -> str:
    return " ".join(s.split())


def verify_quotes(quotes: list[str], text: str) -> tuple[list[str], list[str]]:
    """Cytat musi być dosłownym fragmentem tekstu źródła (z dokładnością do białych znaków)."""
    norm = _ws(text)
    ok, bad = [], []
    for q in quotes[:3]:
        q = str(q)[:300]
        (ok if q.strip() and _ws(q) in norm else bad).append(q)
    return ok, bad
