"""Narzędzia tekstowe: podział na zdania (z polskimi skrótami), tokeny, liczby z jednostkami."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

STRICT_ABBREV = {"prof", "dr", "ok", "np", "tj", "ur", "zm", "św", "im", "al", "ul", "inż", "mgr", "hab", "tzw",
                 "m.in", "ds", "nr", "godz", "przyp", "red", "wg", "ang", "łac", "gen", "płk", "ks", "pt", "tzn"}
STOP = {"oraz", "który", "która", "które", "według", "jest", "była", "było", "przez", "jako", "tego", "także", "się",
        "jego", "with", "that", "this", "from", "the", "and", "dla", "nad", "pod", "roku", "wyniosła", "wynosiła",
        "wyniósł", "został", "została", "około", "ponad", "nam", "nie"}
MONTHS = ("stycz", "lut", "marc", "kwie", "maj", "czerw", "lip", "sierp", "wrze", "paźdz", "pazdz", "listop", "grud")
NUM_WORDS = {"jeden": 1, "jedna": 1, "dwa": 2, "dwie": 2, "dwukrotnie": 2, "twice": 2, "dwóch": 2, "trzy": 3,
             "trzykrotnie": 3, "three": 3, "thrice": 3, "cztery": 4, "czterokrotnie": 4, "pięć": 5, "once": 1,
             "jednokrotnie": 1, "podwójna": 2, "podwójną": 2, "potrójna": 3}
SCALE = {"tys": 1e3, "tysięcy": 1e3, "tysiące": 1e3, "mln": 1e6, "milion": 1e6, "miliony": 1e6, "milionów": 1e6,
         "million": 1e6, "mld": 1e9, "miliard": 1e9, "miliardów": 1e9, "billion": 1e9}
UNITS = {"%": "%", "proc": "%", "procent": "%", "percent": "%", "km": "km", "m": "m", "zł": "pln", "pln": "pln",
         "osób": "count", "osoby": "count", "mieszkańców": "count", "eur": "eur", "euro": "eur"}


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Zwraca zakresy (start, end) zdań; nie dzieli po ścisłych skrótach (prof., np., ok.)."""
    spans: list[tuple[int, int]] = []
    start = 0
    for m in re.finditer(r"[.!?…]+(?=\s+[A-ZĄĆĘŁŃÓŚŹŻ\"„«(])", text):
        before = text[start : m.start()].split()
        last = before[-1].lower().rstrip(".") if before else ""
        if last in STRICT_ABBREV or (len(last) == 1 and last.isalpha() and last != "r"):
            continue
        spans.append((start, m.end()))
        start = m.end()
        while start < len(text) and text[start].isspace():
            start += 1
    if start < len(text) and text[start:].strip():
        spans.append((start, len(text.rstrip())))
    return spans


def strip_diacritics(text: str) -> str:
    t = unicodedata.normalize("NFKD", text)
    return "".join(c for c in t if not unicodedata.combining(c)).replace("ł", "l").replace("Ł", "L")


def tokens(text: str) -> set[str]:
    words = re.findall(r"\w{3,}", text.lower())
    return {strip_diacritics(w)[:5] for w in words if w not in STOP and not w.isdigit()}


@dataclass(frozen=True)
class Quantity:
    value: float
    decimals: int
    scale: float
    unit: str  # %, km, m, pln, count, year, plain…
    raw: str

    def matches(self, other: Quantity, approx: bool = False) -> bool:
        """Porównanie z dokładnością twierdzenia (np. „449 mln” ≈ 449 489 862; „5,1%” ≠ 5,2%)."""
        if self.unit != other.unit and "plain" not in (self.unit, other.unit):
            return False
        step = self.scale * (10 ** -self.decimals)
        tol = step * (5 if approx else 0.5)
        return abs(self.value - other.value) <= tol + 1e-9

    def comparable(self, other: Quantity) -> bool:
        return self.unit == other.unit or {self.unit, other.unit} <= {"count", "plain"}


_NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:[.,](\d+))?(?![\d])\s*([%a-ząćęłńóśźżA-Z.]*)\s*"
                  r"([a-ząćęłńóśźż]*)")


def quantities(text: str) -> list[Quantity]:
    out: list[Quantity] = []
    text = re.sub(r"\b((?:19|20)\d{2})-\d{2}-\d{2}\b", r"\1", text)  # data ISO → sam rok
    text = re.sub(r"\b\d{1,2}\.\d{1,2}\.((?:19|20)\d{2})\b", r"\1", text)  # data dd.mm.rrrr → sam rok
    for m in _NUM.finditer(text):
        int_part, frac, w1, w2 = m.group(1), m.group(2) or "", m.group(3).lower(), m.group(4).lower()
        digits = int_part.replace(" ", "").replace("\u00a0", "")
        after = text[m.end(): m.end() + 12].lower()
        value = float(f"{digits}.{frac}" if frac else digits)
        w1c = w1.rstrip(".")
        if not frac and len(digits) == 4 and 1000 <= value <= 2100 and w1c not in SCALE and w1c not in ("km", "m", "zł", "%"):
            out.append(Quantity(value, 0, 1, "year", m.group(0).strip()))
            continue
        if any(w1c.startswith(mo) for mo in MONTHS) or (not frac and re.match(r"^[-./]\d", text[m.end(1):m.end(1) + 3])):
            continue  # dzień miesiąca / fragment daty
        scale, unit = 1.0, "plain"
        if w1c in SCALE:
            scale = SCALE[w1c]
            unit = UNITS.get(w2, "count")
        elif w1c in UNITS or w1 == "%":
            unit = UNITS.get(w1c, "%")
        elif w1c.startswith("m") and after.startswith(("n.p.m", " n.p.m")) or w1c == "m":
            unit = "m"
        if unit == "plain" and value >= 1000:
            unit = "count"
        out.append(Quantity(value * scale, len(frac), scale, unit, m.group(0).strip()))
    for w, n in NUM_WORDS.items():
        if re.search(rf"\b{w}\b", text.lower()):
            out.append(Quantity(float(n), 0, 1, "times", w))
    return out


def significant(qs: list[Quantity]) -> list[Quantity]:
    return [q for q in qs if q.unit != "year"]


def years(qs: list[Quantity]) -> set[int]:
    return {int(q.value) for q in qs if q.unit == "year"}


def is_approx(text: str) -> bool:
    return bool(re.search(r"\b(około|ok\.|blisko|prawie|ponad|niemal|przeszło|about|around|approximately)\b", text.lower()))
