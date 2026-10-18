"""Walidacja JSON werdyktów (format ze SKILL.md) przed zapisem do newsroom.

Użycie:  python .claude/skills/weryfikacja-faktow/scripts/validate_verdicts.py werdykty.json
Plik: obiekt werdyktu albo lista obiektów. Kod wyjścia 1 = błędy.
Sprawdza: schemat (enum werdyktu, pewność 0–1, uzasadnienie), relacje i oceny źródeł, zgodność z regułami werdyktu.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

VERDICTS = {"potwierdzone", "wątpliwe", "fałszywe"}
RELATIONS = {"supports", "contradicts", "context"}
PRIMARY_MIN, INDEPENDENT_MIN, CONTRADICT_MIN, CONFLICT_MIN = 70, 60, 70, 60


def _host(url: str) -> str:
    return url.split("://", 1)[-1].split("/", 1)[0].lower().removeprefix("www.")


def validate(v: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(v, dict):
        return ["werdykt musi być obiektem JSON"]
    if v.get("verdict") not in VERDICTS:
        errs.append(f"verdict musi być jednym z {sorted(VERDICTS)}")
    conf = v.get("confidence")
    if not isinstance(conf, int | float) or not 0 <= conf <= 1:
        errs.append("confidence musi być liczbą 0–1")
    if not str(v.get("rationale", "")).strip():
        errs.append("brak uzasadnienia (rationale)")
    sources = v.get("sources", [])
    if not isinstance(sources, list):
        return errs + ["sources musi być listą"]
    for i, s in enumerate(sources, 1):
        if s.get("relation") not in RELATIONS:
            errs.append(f"źródło {i}: relation musi być jednym z {sorted(RELATIONS)}")
        score = s.get("credibility_score")
        if not isinstance(score, int | float) or not 0 <= score <= 100:
            errs.append(f"źródło {i}: credibility_score 0–100")
        if s.get("relation") in ("supports", "contradicts") and not str(s.get("quote", "")).strip():
            errs.append(f"źródło {i}: relacja rozstrzygająca wymaga dosłownego cytatu")
        if not str(s.get("url", "")).startswith(("http://", "https://")):
            errs.append(f"źródło {i}: nieprawidłowy url")
    ok = [s for s in sources if not s.get("injection_high")]
    sup = [s for s in ok if s.get("relation") == "supports"]
    con = [s for s in ok if s.get("relation") == "contradicts"]
    verdict = v.get("verdict")
    if verdict == "potwierdzone":
        primary = any(s.get("credibility_score", 0) >= PRIMARY_MIN and s.get("is_primary", True) for s in sup)
        indep = len({_host(s.get("url", "")) for s in sup if s.get("credibility_score", 0) >= INDEPENDENT_MIN}) >= 2
        if not (primary or indep):
            errs.append("„potwierdzone” wymaga źródła pierwotnego ≥ 70 albo 2 niezależnych ≥ 60")
        if any(s.get("credibility_score", 0) >= CONFLICT_MIN for s in con):
            errs.append("„potwierdzone” mimo wiarygodnego źródła przeczącego")
    if verdict == "fałszywe" and not any(s.get("credibility_score", 0) >= CONTRADICT_MIN for s in con):
        errs.append("„fałszywe” wymaga wiarygodnego (≥ 70) źródła przeczącego")
    return errs


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # konsola Windows (cp1250)
    if len(argv) != 2:
        print(__doc__)
        return 2
    data = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else [data]
    failed = 0
    for n, item in enumerate(items, 1):
        errs = validate(item)
        label = item.get("claim_id", n) if isinstance(item, dict) else n
        if errs:
            failed += 1
            print(f"✘ twierdzenie {label}:")
            for e in errs:
                print(f"   - {e}")
        else:
            print(f"✔ twierdzenie {label}: OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
