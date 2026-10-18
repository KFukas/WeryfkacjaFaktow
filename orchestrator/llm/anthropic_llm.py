"""Implementacja etapów na prawdziwym modelu Claude (Anthropic Python SDK).

* Etapy bez narzędzi (ekstrakcja, plan, kwarantanna, werdykt) używają structured outputs
  (`output_config.format` = JSON Schema) — wynik zawsze zgodny ze schematem.
* Etap research to pętla tool-use z narzędziami `strict: true` wyłącznie ze strefy nieufnej (allowlista).
* Prompty systemowe pochodzą z pliku skilla i są cache'owane (`cache_control`).
* Serwerowy fallback przy odmowie (`fallbacks: "default"`) — wyłączany `ANTHROPIC_FALLBACKS=off`.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic

from orchestrator import prompts
from orchestrator.llm.base import (
    EXTRACT_SCHEMA,
    PLAN_SCHEMA,
    QUARANTINE_SCHEMA,
    VERDICT_SCHEMA,
    StageResult,
    Usage,
)

# USD za 1 mln tokenów (wejście, wyjście). Odczyt z cache ~0,1× ceny wejścia, zapis ~1,25×.
PRICING = {"claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0), "claude-haiku-5-5": (0.10, 0.50),
           "claude-fable-5-1": (10.0, 50.0)}
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_RESEARCH_TURNS = 8


class LLMRefusal(RuntimeError):
    pass


def _usage(model: str, u: Any) -> Usage:
    price_in, price_out = PRICING.get(model, (4.0, 20.0))
    inp = getattr(u, "input_tokens", 0) or 0
    out = getattr(u, "output_tokens", 0) or 0
    cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0
    cost = (inp * price_in + cache_read * price_in * 0.1 + cache_write * price_in * 1.25 + out * price_out) / 1e6
    return Usage(inp + cache_read + cache_write, out, round(cost, 6))


class AnthropicLLM:
    provider = "anthropic"

    def __init__(self, settings: Any):
        self.settings = settings
        self.model = settings.anthropic_model
        self.quarantine_model = settings.anthropic_quarantine_model or settings.anthropic_model
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None, max_retries=3,
                                               timeout=180.0)

    # ------------------------------------------------------------------ core
    async def _create(self, model: str, stage: str, messages: list[dict], schema: dict | None = None,
                      tools: list[dict] | None = None, max_tokens: int = 8000) -> Any:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": prompts.system_prompt(stage), "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": {"effort": self.settings.anthropic_effort},
        }
        if schema is not None:
            kwargs["output_config"]["format"] = {"type": "json_schema", "schema": schema}
        if tools:
            kwargs["tools"] = tools
        try:
            if self.settings.anthropic_fallbacks == "default":
                resp = await self.client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            else:
                resp = await self.client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            raise
        except anthropic.APIStatusError as exc:
            raise RuntimeError(f"błąd API Anthropic ({exc.status_code}): {exc.message[:300]}") from exc
        if resp.stop_reason == "refusal":
            cat = getattr(getattr(resp, "stop_details", None), "category", None)
            raise LLMRefusal(f"model odmówił odpowiedzi (kategoria: {cat})")
        return resp

    async def _json_stage(self, stage: str, schema: dict, user: str, model: str | None = None,
                          max_tokens: int = 8000) -> StageResult:
        model = model or self.model
        resp = await self._create(model, stage, [{"role": "user", "content": user}], schema=schema,
                                  max_tokens=max_tokens)
        if resp.stop_reason == "max_tokens":
            raise RuntimeError(f"etap {stage}: przekroczono max_tokens")
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        data = json.loads(text)
        return StageResult(data, _usage(model, resp.usage), audit={
            "stage": stage, "model": getattr(resp, "model", model), "prompt_hash": prompts.prompt_hash(stage),
            "request_id": getattr(resp, "_request_id", None), "user_prompt": user[:20_000], "response": text[:20_000]})

    # ---------------------------------------------------------------- stages
    async def extract_claims(self, title: str, body: str) -> StageResult:
        user = (f"TYTUŁ: {title}\n\nTREŚĆ ARTYKUŁU (offsety liczone od pierwszego znaku po znaczniku):\n"
                f"<article>{body}</article>")
        return await self._json_stage("extract", EXTRACT_SCHEMA, user, max_tokens=16000)

    async def plan(self, claim: dict[str, Any]) -> StageResult:
        user = f"TWIERDZENIE ({claim.get('category', 'inne')}): {claim['text']}"
        return await self._json_stage("plan", PLAN_SCHEMA, user, max_tokens=2000)

    async def quarantine(self, claim: dict[str, Any], source_id: str, wrapped_source: str, raw_text: str) -> StageResult:
        user = f"TWIERDZENIE: {claim['text']}\n\nŹRÓDŁO {source_id}:\n{wrapped_source}"
        return await self._json_stage("quarantine", QUARANTINE_SCHEMA, user, model=self.quarantine_model,
                                      max_tokens=3000)

    async def verdict(self, claim: dict[str, Any], evidence_view: str, evidence: list[dict[str, Any]]) -> StageResult:
        user = f"TWIERDZENIE ({claim.get('category', 'inne')}): {claim['text']}\n\nŹRÓDŁA:\n{evidence_view}"
        return await self._json_stage("verdict", VERDICT_SCHEMA, user, max_tokens=6000)

    async def research(self, claim: dict[str, Any], plan: dict[str, Any], tools) -> StageResult:
        defs = tools.tool_definitions()
        messages: list[dict] = [{"role": "user", "content": (
            f"TWIERDZENIE ({claim.get('category', 'inne')}): {claim['text']}\n"
            f"PLAN: {json.dumps(plan, ensure_ascii=False)}\n"
            f"Limit: {tools.max_sources} źródeł. Znajdź źródła, które rozstrzygają twierdzenie.")}]
        usage = Usage()
        transcript: list[dict] = []
        final_text = ""
        for _turn in range(MAX_RESEARCH_TURNS):
            resp = await self._create(self.model, "research", messages, tools=defs, max_tokens=8000)
            usage.add(_usage(self.model, resp.usage))
            messages.append({"role": "assistant", "content": resp.content})
            calls = [b for b in resp.content if b.type == "tool_use"]
            final_text = " ".join(b.text for b in resp.content if b.type == "text")
            if resp.stop_reason != "tool_use" or not calls:
                break
            results = []
            for call in calls:
                args = call.input if isinstance(call.input, dict) else {}
                outcome = await tools.call(call.name, args)
                transcript.append({"tool": call.name, "args": args})
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": outcome.view,
                                **({"is_error": True} if outcome.is_error else {})})
            messages.append({"role": "user", "content": results})
        return StageResult({"summary": final_text[:2000]}, usage,
                           audit={"stage": "research", "prompt_hash": prompts.prompt_hash("research"),
                                  "tool_calls": transcript})
