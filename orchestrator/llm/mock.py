"""Deterministyczny model offline (bez kosztów i klucza API) — heurystyki zamiast LLM.

Służy do CI, demonstracji i testów red-team trybu offline. Nie „rozumie” tekstu: porównuje liczby z jednostkami,
lata i słowa kluczowe. Celowo jest konserwatywny — gdy nie ma pewności, wybiera „context”/„wątpliwe”.
"""

from __future__ import annotations

import re
from typing import Any

from orchestrator import textnum
from orchestrator.llm.base import StageResult
from orchestrator.verdict_rules import Evidence, decide

CAUSAL = re.compile(r"\b(spowodowan\w*|z powodu|dlatego|w wyniku|przyczyn\w*|wskutek|skutkiem)\b", re.I)
QUOTE = re.compile(r"\b(powiedział\w*|stwierdził\w*|oświadczył\w*|według słów|cytuj\w*)\b|[„\"«]", re.I)
COMPARE = re.compile(r"\b(najwyższ\w*|najdłuższ\w*|najludniejsz\w*|największ\w*|najmniejsz\w*|więcej niż|mniej niż|"
                     r"rekordow\w*)\b", re.I)
OPINION = re.compile(r"\b(spodziewa\w*|prognoz\w*|warto|powinn\w*|uważa\w*|inspiruj\w*|zaskoczyć|zmieniał\w*)\b", re.I)
GREATER = re.compile(r"\b(przekroczył\w*|ponad|powyżej|więcej niż|przeszło)\b", re.I)
LESS = re.compile(r"\b(poniżej|mniej niż|nie przekroczył\w*)\b", re.I)
API_PROVIDERS = {"nbp", "gus_bdl", "krs", "wikidata", "dane_gov"}


def _category(sentence: str) -> str:
    qs = textnum.quantities(sentence)
    if QUOTE.search(sentence):
        return "cytat"
    if CAUSAL.search(sentence):
        return "przyczynowe"
    if textnum.significant(qs):
        return "liczbowe"
    if textnum.years(qs) or re.search(r"\b\d{1,2} (stycz|lut|mar|kwie|maj|czerw|lip|sierp|wrze|paźdz|listop|grud)", sentence):
        return "datowe"
    if COMPARE.search(sentence):
        return "porównawcze"
    return "inne"


def _checkable(sentence: str) -> bool:
    if OPINION.search(sentence):
        return False
    qs = textnum.quantities(sentence)
    return bool(qs or QUOTE.search(sentence) or CAUSAL.search(sentence) or COMPARE.search(sentence))


def judge_sentence(claim: str, sentence: str) -> str | None:
    ct, st = textnum.tokens(claim), textnum.tokens(sentence)
    overlap = len(ct & st)
    cq, sq = textnum.quantities(claim), textnum.quantities(sentence)
    csig, ssig = textnum.significant(cq), textnum.significant(sq)
    cy, sy = textnum.years(cq), textnum.years(sq)
    approx = textnum.is_approx(claim)
    if overlap < 2 and not (csig and any(c.matches(s, approx) for c in csig for s in ssig) and overlap >= 1):
        return None
    if csig:
        if cy and sy and not (cy & sy):
            return None  # inny okres
        greater, less = GREATER.search(claim), LESS.search(claim)
        for c in csig:
            for s in ssig:
                if not (c.comparable(s) or "plain" in (c.unit, s.unit)):
                    continue
                if greater and c.comparable(s):
                    return "supports" if s.value > c.value else "contradicts"
                if less and c.comparable(s):
                    return "supports" if s.value < c.value else "contradicts"
                if c.matches(s, approx):
                    return "supports"
        if any(c.comparable(s) for c in csig for s in ssig):
            return "contradicts"
        return "context"
    if cy:
        if cy & sy:
            return "supports"
        return "contradicts" if sy else "context"
    return "context"


def source_sentences(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip(" |")
        if not line:
            continue
        out += [line[a:b].strip() for a, b in textnum.split_sentences(line)]
    return [s for s in out if len(s) > 8]


class MockLLM:
    provider = "mock"
    model = "mock-heuristic-1"

    async def extract_claims(self, title: str, body: str) -> StageResult:
        claims = []
        for a, b in textnum.split_sentences(body):
            sent = body[a:b]
            if _checkable(sent):
                claims.append({"text": sent, "start_offset": a, "end_offset": b, "category": _category(sent),
                               "checkable": True})
        return StageResult({"claims": claims}, audit={"note": "heurystyka: zdania z liczbami/datami/cytatami"})

    async def plan(self, claim: dict[str, Any]) -> StageResult:
        years = sorted(textnum.years(textnum.quantities(claim["text"])))
        return StageResult({"queries": [claim["text"]], "source_types": [],
                            "claim_period": str(years[-1]) if years else ""})

    async def research(self, claim: dict[str, Any], plan: dict[str, Any], tools) -> StageResult:
        seen: set[str] = set()
        results: list[dict] = []
        for q in plan.get("queries", [])[:3]:
            out = await tools.call("search_public_sources", {"query": q, "limit": 6})
            for r in out.data.get("results", []):
                if r["url"] not in seen:
                    seen.add(r["url"])
                    results.append(r)
        results.sort(key=lambda r: -r.get("relevance", 0))
        for r in results[: tools.max_sources]:
            if r.get("dataset"):
                d = r["dataset"]
                await tools.call("query_dataset", {"provider": d["provider"], "dataset_id": d["dataset_id"],
                                                   "params": d.get("params", {})})
            if r.get("provider") not in API_PROVIDERS:
                await tools.call("fetch_url_sanitized", {"url": r["url"]})
        return StageResult({"summary": f"przejrzano {min(len(results), tools.max_sources)} wyników"})

    async def quarantine(self, claim: dict[str, Any], source_id: str, wrapped_source: str, raw_text: str) -> StageResult:
        judged: list[tuple[str, str]] = []
        for sent in source_sentences(raw_text):
            stance = judge_sentence(claim["text"], sent)
            if stance:
                judged.append((stance, sent))
        stances = {s for s, _ in judged}
        if "supports" in stances and "contradicts" in stances:
            stance = "context"
        elif "supports" in stances:
            stance = "supports"
        elif "contradicts" in stances:
            stance = "contradicts"
        elif stances:
            stance = "context"
        else:
            stance = "unrelated"
        order = {"supports": 0, "contradicts": 0, "context": 1}
        quotes = [s[:300] for st, s in sorted(judged, key=lambda t: order[t[0]])][:3]
        summary = {"supports": "Źródło podaje wartości zgodne z twierdzeniem.",
                   "contradicts": "Źródło podaje inne wartości dla tego samego faktu.",
                   "context": "Źródło dotyczy tematu, ale nie rozstrzyga twierdzenia (lub jest wewnętrznie niejednoznaczne).",
                   "unrelated": "Źródło nie dotyczy twierdzenia."}[stance]
        return StageResult({"relevant": stance != "unrelated", "stance": stance, "quotes": quotes, "summary": summary,
                            "manipulation_notes": []})

    async def verdict(self, claim: dict[str, Any], evidence_view: str, evidence: list[dict[str, Any]]) -> StageResult:
        sources = []
        rule_input = []
        for e in evidence:
            relation = e["stance"] if e["stance"] in ("supports", "contradicts") else "context"
            sources.append({"source_id": e["key"], "relation": relation, "credibility_adjustment": 0,
                            "adjustment_reason": "model offline nie koryguje oceny"})
            rule_input.append(Evidence(e["key"], e["score"], relation, e["is_primary"], e["group"],
                                       e["high_injection"], e["lookalike"]))
        rule = decide(rule_input)
        basis = ", ".join(f"[{k}]" for k in rule.basis) or "brak"
        rationale = {
            "potwierdzone": f"Twierdzenie znajduje potwierdzenie w wiarygodnych źródłach ({basis}).",
            "fałszywe": f"Wiarygodne źródło podaje inne dane niż twierdzenie ({basis}).",
            "wątpliwe": "Nie udało się rozstrzygnąć twierdzenia: " + "; ".join(rule.reasons[-1:]) + ".",
        }[rule.verdict]
        manip = [f"[{e['key']}] {f}" for e in evidence for f in e.get("flag_types", [])
                 if f in ("instruction_override", "tool_instruction", "verdict_manipulation", "role_marker",
                          "exfiltration", "hidden_visible_mismatch", "self_declared_credibility")]
        return StageResult({"sources": sources, "verdict": rule.verdict,
                            "confidence": round(rule.max_confidence * 0.95, 3), "rationale": rationale,
                            "manipulation_detected": manip})
