"""Wspólny interfejs modeli językowych orkiestratora + schematy JSON wyjścia etapów."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

CATEGORIES = ["liczbowe", "datowe", "cytat", "przyczynowe", "porównawcze", "inne"]
SOURCE_TYPES = ["official_statistics", "public_register", "primary_data", "government", "intergovernmental",
                "scientific", "established_media", "encyclopedia"]
STANCES = ["supports", "contradicts", "context", "unrelated"]
RELATIONS = ["supports", "contradicts", "context"]
VERDICTS = ["potwierdzone", "wątpliwe", "fałszywe"]


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_STR = {"type": "string"}
_STRS = {"type": "array", "items": {"type": "string"}}

EXTRACT_SCHEMA = _obj({"claims": {"type": "array", "items": _obj({
    "text": _STR, "start_offset": {"type": "integer"}, "end_offset": {"type": "integer"},
    "category": {"type": "string", "enum": CATEGORIES}, "checkable": {"type": "boolean"}})}})
PLAN_SCHEMA = _obj({"queries": _STRS, "source_types": {"type": "array", "items": {"type": "string", "enum": SOURCE_TYPES}},
                    "claim_period": _STR})
QUARANTINE_SCHEMA = _obj({"relevant": {"type": "boolean"}, "stance": {"type": "string", "enum": STANCES},
                          "quotes": _STRS, "summary": _STR, "manipulation_notes": _STRS})
VERDICT_SCHEMA = _obj({
    "sources": {"type": "array", "items": _obj({"source_id": _STR, "relation": {"type": "string", "enum": RELATIONS},
                                                "credibility_adjustment": {"type": "integer"},
                                                "adjustment_reason": _STR})},
    "verdict": {"type": "string", "enum": VERDICTS}, "confidence": {"type": "number"}, "rationale": _STR,
    "manipulation_detected": _STRS})


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cost_usd = round(self.cost_usd + other.cost_usd, 6)


@dataclass
class StageResult:
    data: dict[str, Any]
    usage: Usage = field(default_factory=Usage)
    audit: dict[str, Any] = field(default_factory=dict)


class ResearchTools(Protocol):
    """Narzędzia dostępne modelowi w etapie research — każde wywołanie przechodzi przez bramkę (gateway)."""

    async def call(self, name: str, args: dict[str, Any]) -> str: ...

    def tool_definitions(self) -> list[dict[str, Any]]: ...


class LLM(Protocol):
    provider: str
    model: str

    async def extract_claims(self, title: str, body: str) -> StageResult: ...

    async def plan(self, claim: dict[str, Any]) -> StageResult: ...

    async def research(self, claim: dict[str, Any], plan: dict[str, Any], tools: ResearchTools) -> StageResult: ...

    async def quarantine(self, claim: dict[str, Any], source_id: str, wrapped_source: str, raw_text: str) -> StageResult: ...

    async def verdict(self, claim: dict[str, Any], evidence_view: str, evidence: list[dict[str, Any]]) -> StageResult: ...


def get_llm(provider: str, settings: Any, **kwargs: Any) -> LLM:
    if provider == "anthropic":
        from orchestrator.llm.anthropic_llm import AnthropicLLM

        return AnthropicLLM(settings)
    if provider == "gullible":
        from orchestrator.llm.gullible import GullibleLLM

        return GullibleLLM(**kwargs)
    from orchestrator.llm.mock import MockLLM

    return MockLLM()
