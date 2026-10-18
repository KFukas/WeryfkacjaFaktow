"""Normalizacja Unicode: znaki niewidoczne, bidi, Unicode Tags, homoglify."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

ZERO_WIDTH = {
    "\u200b", "\u200c", "\u200d", "\u2060", "\u2061", "\u2062", "\u2063", "\u2064", "\ufeff", "\u180e",
    "\u00ad",  # miękki dywiz
    "͏", "ᅟ", "ᅠ", "ㅤ", "ﾠ",
}
BIDI_MARKS = {"\u200e", "\u200f", "\u061c"}  # LRM/RLM — częste w legalnych tekstach wielojęzycznych
BIDI_CONTROLS = {"\u202a", "\u202b", "\u202c", "\u202d", "\u202e", "\u2066", "\u2067", "\u2068", "\u2069"}
BIDI = BIDI_MARKS | BIDI_CONTROLS
TAGS_RANGE = (0xE0000, 0xE007F)
VARIATION_SELECTORS = re.compile("[︀-️\U000e0100-\U000e01ef]")

# Mapowanie najczęstszych homoglifów (cyrylica/greka → łacina) na „szkielet” do wykrywania fraz.
CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s",
    "ԁ": "d", "ɡ": "g", "һ": "h", "ӏ": "l", "ո": "n", "ս": "u", "ν": "v", "ԝ": "w",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T",
    "Х": "X", "У": "Y", "І": "I", "Ј": "J", "Ѕ": "S",
    "α": "a", "ο": "o", "ρ": "p", "τ": "t", "ι": "i", "κ": "k", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z",
    "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Χ": "X", "Υ": "Y",
})
_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass
class UnicodeReport:
    zero_width: int = 0
    bidi: int = 0
    bidi_controls: int = 0  # osadzenia/nadpisania kierunku (U+202A–U+202E, U+2066–U+2069) — typowe w atakach
    tags: int = 0
    tag_payload: str = ""  # ASCII ukryty w Unicode Tags
    variation_selectors: int = 0


def decode_tags(text: str) -> str:
    """Unicode Tags (U+E0020–U+E007E) kodują ASCII „niewidocznym atramentem” — odkodowujemy do analizy."""
    return "".join(chr(ord(ch) - 0xE0000) for ch in text if 0xE0020 <= ord(ch) <= 0xE007E)


def clean(text: str, report: UnicodeReport | None = None) -> str:
    """Usuwa znaki niewidoczne/sterujące i normalizuje do NFKC. Statystyki dopisuje do `report`."""
    rep = report if report is not None else UnicodeReport()
    payload = decode_tags(text)
    if payload:
        rep.tag_payload += payload
    out: list[str] = []
    for ch in text:
        cp = ord(ch)
        if TAGS_RANGE[0] <= cp <= TAGS_RANGE[1]:
            rep.tags += 1
        elif ch in ZERO_WIDTH:
            rep.zero_width += 1
        elif ch in BIDI:
            rep.bidi += 1
            if ch in BIDI_CONTROLS:
                rep.bidi_controls += 1
        elif unicodedata.category(ch) == "Cc" and ch not in "\n\t\r":
            continue
        else:
            out.append(ch)
    joined = "".join(out)
    vs = VARIATION_SELECTORS.findall(joined)
    if vs:
        rep.variation_selectors += len(vs)
        joined = VARIATION_SELECTORS.sub("", joined)
    return unicodedata.normalize("NFKC", joined)


def skeleton(text: str) -> str:
    """Wersja tekstu z homoglifami zamienionymi na łacinę i bez diakrytyków — do dopasowań wzorców."""
    t = unicodedata.normalize("NFKC", text).translate(CONFUSABLES)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return t.replace("ł", "l").replace("Ł", "L").lower()


def _script(ch: str) -> str | None:
    if not ch.isalpha():
        return None
    name = unicodedata.name(ch, "")
    for script in ("LATIN", "CYRILLIC", "GREEK", "ARMENIAN", "CHEROKEE"):
        if name.startswith(script):
            return script
    return "OTHER"


def mixed_script_words(text: str, limit: int = 5) -> list[str]:
    """Słowa łączące alfabet łaciński z cyrylicą/greką — typowy ślad homoglifów."""
    found: list[str] = []
    for m in _WORD.finditer(text):
        word = m.group(0)
        scripts = {s for s in map(_script, word) if s}
        if "LATIN" in scripts and scripts & {"CYRILLIC", "GREEK", "ARMENIAN", "CHEROKEE"}:
            found.append(word)
            if len(found) >= limit:
                break
    return found
