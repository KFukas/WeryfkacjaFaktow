"""Deterministyczna (nie-LLM-owa) część oceny wiarygodności źródła — zob. config/credibility_rubric.yaml.

Typ źródła wynika WYŁĄCZNIE z domeny (tabela w rubryce). Metadane deklarowane przez stronę (wydawca, „oficjalne
źródło”…) mogą jedynie obniżyć wynik — nigdy go podnieść ponad to, co daje domena.
"""

from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from mcp_servers.web_sandbox.unicode_tools import mixed_script_words, skeleton

MULTI_LABEL_SUFFIXES = ("gov.pl", "com.pl", "org.pl", "edu.pl", "net.pl", "info.pl", "waw.pl", "co.uk", "ac.uk",
                        "gov.uk", "com.au")


@lru_cache(maxsize=4)
def load_rubric(path: str) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def registrable(host: str) -> str:
    labels = host.lower().strip(".").split(".")
    for suf in MULTI_LABEL_SUFFIXES:
        if host.endswith("." + suf):
            return ".".join(labels[-3:]) if len(labels) >= 3 else host
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def _levenshtein(a: str, b: str, cap: int = 3) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _decode_idna(host: str) -> str:
    try:
        return host.encode("ascii").decode("idna") if "xn--" in host else host
    except UnicodeError:
        return host


def classify_domain(host: str, rubric: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    host = host.lower().strip(".")
    best: tuple[str, dict[str, Any]] | None = None
    for dom, info in rubric["domains"].items():
        if host == dom or host.endswith("." + dom):
            if best is None or len(dom) > len(best[0]):
                best = (dom, info)
    return best


def lookalike_reason(host: str, rubric: dict[str, Any]) -> str | None:
    """Wykrywa domeny-podróbki: homoglify/punycode, literówki, znana domena „wklejona” w obcą, marka w obcej domenie."""
    host = host.lower().strip(".")
    if classify_domain(host, rubric) is not None:
        return None
    known = list(rubric["domains"].keys())
    decoded = _decode_idna(host)
    if decoded != host or mixed_script_words(decoded):
        sk = skeleton(decoded)
        for dom in known:
            if sk == dom or sk.endswith("." + dom):
                return f"homoglify/punycode udające {dom}"
        return "domena IDN (punycode) — podwyższone ryzyko podszycia"
    for dom in known:
        if f"{dom}." in host or host.startswith(dom.replace(".", "-")):
            return f"znana domena {dom} osadzona w obcej domenie"
    reg = registrable(host)
    for dom in known:
        kreg = registrable(dom)
        if len(kreg) >= 6 and reg != kreg and _levenshtein(reg, kreg) <= 2:
            return f"literówka znanej domeny {kreg}"
    tokens = set(re.split(r"[.\-_]", host))
    brands = set(rubric.get("protected_brands", []))
    hit = tokens & brands
    if hit:
        return f"marka „{sorted(hit)[0]}” w domenie spoza listy oficjalnych"
    return None


def _year(value: Any) -> int | None:
    if not value:
        return None
    m = re.search(r"(19|20)\d{2}", str(value))
    return int(m.group(0)) if m else None


def score_source(url: str, metadata: dict[str, Any] | None, rubric_path: str) -> dict[str, Any]:
    rubric = load_rubric(str(rubric_path))
    meta = metadata or {}
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    breakdown: list[dict[str, Any]] = []
    mods, pens = rubric["modifiers"], rubric["penalties"]

    match = classify_domain(host, rubric)
    lookalike = lookalike_reason(host, rubric) if host else None
    if match and not lookalike:
        dom, info = match
        stype, publisher, group = info["type"], info["publisher"], info.get("group", dom)
    else:
        stype, publisher, group = "unknown", "", registrable(host) if host else ""
    if group == "*":
        group = registrable(host)
    tinfo = rubric["source_types"][stype]
    is_primary = bool(tinfo.get("primary"))
    score = tinfo["base"]
    breakdown.append({"criterion": "typ_zrodla", "points": tinfo["base"],
                      "detail": f"{tinfo['label']} ({match[0] if match and not lookalike else host or '?'})"})

    if is_primary:
        score += mods["primary_bonus"]
        breakdown.append({"criterion": "pierwotne", "points": mods["primary_bonus"], "detail": "źródło pierwotne"})
    elif stype in ("encyclopedia", "established_media", "other_media"):
        score += mods["secondary_penalty"]
        breakdown.append({"criterion": "wtorne", "points": mods["secondary_penalty"], "detail": "źródło wtórne"})
    if meta.get("published_at"):
        score += mods["has_date"]
        breakdown.append({"criterion": "data", "points": mods["has_date"], "detail": "znana data publikacji"})
    if meta.get("author") or (match and not lookalike):
        score += mods["has_author"]
        breakdown.append({"criterion": "autor", "points": mods["has_author"], "detail": "znany autor/instytucja"})
    if meta.get("has_methodology"):
        score += mods["has_methodology"]
        breakdown.append({"criterion": "metodologia", "points": mods["has_methodology"], "detail": "opis metodologii"})
    if meta.get("structured_api") and match and not lookalike:
        score += mods["structured_api"]
        breakdown.append({"criterion": "api", "points": mods["structured_api"], "detail": "dane z oficjalnego API"})
    if parts.scheme != "https":
        score += mods["no_https"]
        breakdown.append({"criterion": "https", "points": mods["no_https"], "detail": "brak HTTPS"})
    claim_year, pub_year = _year(meta.get("claim_period")), _year(meta.get("published_at"))
    if claim_year and pub_year and pub_year < claim_year:
        score += mods["stale"]
        breakdown.append({"criterion": "aktualnosc", "points": mods["stale"],
                          "detail": f"źródło z {pub_year} r., twierdzenie dotyczy {claim_year} r."})
    if meta.get("subject_is_publisher"):
        score += mods["conflict_of_interest"]
        breakdown.append({"criterion": "konflikt_interesow", "points": mods["conflict_of_interest"],
                          "detail": "wydawca jest podmiotem twierdzenia"})

    # Kary
    flags = meta.get("injection_flags") or []
    inj = 0
    for f in flags:
        inj += {"high": pens["injection_high"], "medium": pens["injection_medium"]}.get(f.get("severity"),
                                                                                         pens["injection_low"])
    inj = max(inj, pens["injection_cap"])
    if inj:
        score += inj
        n_high = sum(1 for f in flags if f.get("severity") == "high")
        breakdown.append({"criterion": "injection", "points": inj,
                          "detail": f"{len(flags)} flag manipulacji (w tym {n_high} high)"})
    types = {f.get("type") for f in flags}
    if "hidden_visible_mismatch" in types:
        score += pens["hidden_visible_mismatch"]
        breakdown.append({"criterion": "ukryte_vs_widoczne", "points": pens["hidden_visible_mismatch"],
                          "detail": "treść ukryta sprzeczna z widoczną"})
    if "self_declared_credibility" in types:
        score += pens["self_declared_credibility"]
        breakdown.append({"criterion": "samozwancza_wiarygodnosc", "points": pens["self_declared_credibility"],
                          "detail": "strona sama deklaruje swoją wiarygodność — ignorujemy i karzemy"})
    if lookalike:
        score += pens["lookalike_domain"]
        breakdown.append({"criterion": "domena_podrobka", "points": pens["lookalike_domain"], "detail": lookalike})
    claimed = str(meta.get("publisher_claimed") or meta.get("publisher") or "")
    if claimed and stype == "unknown" and re.search(r"gus|urz[aą]d statystyczny|nbp|eurostat|ministerstw|rz[aą]d",
                                                    claimed, re.I):
        breakdown.append({"criterion": "deklaracja_wydawcy", "points": 0,
                          "detail": f"strona deklaruje wydawcę „{claimed[:60]}” — niezweryfikowane, bez wpływu"})

    final = max(0, min(100, int(round(score))))
    return {
        "url": url,
        "host": host,
        "score": final,
        "source_type": stype,
        "publisher": publisher,
        "independence_group": group,
        "is_primary": is_primary and not lookalike,
        "lookalike": lookalike,
        "breakdown": breakdown,
        "rubric_version": rubric.get("version", 1),
        "computed_on": date.today().isoformat(),
    }
