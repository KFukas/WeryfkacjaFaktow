"""Deterministyczne reguły werdyktu (docs/METODOLOGIA.md) — ostatnia instancja przed zapisem.

Model językowy proponuje relacje źródeł i werdykt, ale to te reguły decydują, czy dowody na werdykt pozwalają:
* potwierdzone — ≥1 źródło pierwotne (score ≥ 70) wspiera albo ≥2 niezależne (≥ 60) wspierają, bez wiarygodnej
  sprzeczności (źródło ≥ 60 przeczy);
* fałszywe — wiarygodne źródło (≥ 70) bezpośrednio przeczy (i nie ma równie mocnego źródła pierwotnego „za”);
* wątpliwe — wszystko inne.
Źródło z flagą injection o wadze „high” nigdy nie kwalifikuje się jako podstawa werdyktu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

RUBRIC_PATH = Path(__file__).resolve().parent.parent / "config" / "credibility_rubric.yaml"


@lru_cache(maxsize=1)
def thresholds() -> dict[str, int]:
    return yaml.safe_load(RUBRIC_PATH.read_text(encoding="utf-8"))["verdict_rules"]


@dataclass
class Evidence:
    source_key: str
    score: int
    relation: str  # supports | contradicts | context
    is_primary: bool = False
    group: str = ""
    high_injection: bool = False
    lookalike: bool = False

    @property
    def qualifies(self) -> bool:
        return not self.high_injection and not self.lookalike


@dataclass
class RuleOutcome:
    verdict: str
    reasons: list[str] = field(default_factory=list)
    basis: list[str] = field(default_factory=list)  # klucze źródeł, na których oparto werdykt
    max_confidence: float = 0.5


def decide(evidence: list[Evidence]) -> RuleOutcome:
    t = thresholds()
    usable = [e for e in evidence if e.qualifies]
    excluded = [e for e in evidence if not e.qualifies]
    reasons = [f"źródło {e.source_key} pominięte jako podstawa (flagi manipulacji/podróbka domeny)" for e in excluded
               if e.relation != "context"]
    sup = [e for e in usable if e.relation == "supports"]
    con = [e for e in usable if e.relation == "contradicts"]

    strong_primary_sup = [e for e in sup if e.is_primary and e.score >= t["confirm_primary_min"]]
    indep_groups = {e.group or e.source_key for e in sup if e.score >= t["confirm_independent_min"]}
    credible_con = [e for e in con if e.score >= t["credible_conflict_min"]]
    strong_con = [e for e in con if e.score >= t["contradict_min"]]

    if strong_con and not strong_primary_sup:
        return RuleOutcome("fałszywe", reasons + [f"wiarygodne źródło przeczy ({', '.join(e.source_key for e in strong_con)})"],
                           [e.source_key for e in strong_con], max_confidence=0.95 if len(strong_con) > 1 else 0.85)
    confirmable = strong_primary_sup or len(indep_groups) >= t["confirm_independent_count"]
    if confirmable and not credible_con:
        basis = strong_primary_sup or [e for e in sup if e.score >= t["confirm_independent_min"]]
        n = len({e.group or e.source_key for e in basis})
        return RuleOutcome("potwierdzone", reasons + ["spełniony próg potwierdzenia"], [e.source_key for e in basis],
                           max_confidence=min(0.97, 0.8 + 0.07 * n))
    if confirmable and credible_con:
        reasons.append("źródła wiarygodne są ze sobą sprzeczne")
    elif strong_con and strong_primary_sup:
        reasons.append("silne źródła pierwotne wspierają i przeczą — sprzeczność")
    elif sup:
        reasons.append("tylko słabe lub zależne źródła wspierające — poniżej progu")
    elif con:
        reasons.append("przeczą tylko źródła poniżej progu wiarygodności")
    else:
        reasons.append("brak źródeł bezpośrednio odnoszących się do twierdzenia")
    return RuleOutcome("wątpliwe", reasons, [], max_confidence=0.6)


def reconcile(rule: RuleOutcome, proposed: str, proposed_confidence: float) -> tuple[str, float, list[str]]:
    """Werdykt końcowy: zgodny z regułami; przy niezgodności modelu i reguł — „wątpliwe”."""
    notes: list[str] = []
    if proposed == rule.verdict:
        return rule.verdict, round(min(proposed_confidence, rule.max_confidence), 3), notes
    if rule.verdict == "wątpliwe":
        notes.append(f"model proponował „{proposed}”, ale dowody nie spełniają reguł — obniżono do „wątpliwe”")
    else:
        notes.append(f"reguły wskazują „{rule.verdict}”, model „{proposed}” — rozbieżność, oznaczono „wątpliwe”")
    return "wątpliwe", round(min(proposed_confidence, 0.5), 3), notes
