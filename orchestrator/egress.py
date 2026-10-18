"""Strażnik ruchu wychodzącego: dane redakcji nie mogą opuścić systemu w zapytaniach i URL-ach.

Każde wywołanie narzędzia sandboksa (zapytanie wyszukiwania, parametry zbioru, URL do pobrania) jest sprawdzane:
* tokeny-kanarki / oznaczenia poufności (np. `KANAREK-…`, `[POUFNE]`),
* fragmenty treści artykułu (okna ≥ 24 znaków), które nie należą do badanego twierdzenia,
* długie bloki base64 / hex (zakodowane dane),
* nietypowo długie URL-e i parametry.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, unquote_plus, urlsplit

SENSITIVE = re.compile(r"(KANAREK|CANARY)[-_][A-Z0-9]{4,}|\[POUFNE\]|\[NIE DO PUBLIKACJI\]|notatka wewn[eę]trzna",
                       re.IGNORECASE)
WINDOW = 24
MAX_URL = 600
MAX_PARAM = 200


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", unquote_plus(text or "")).lower()
    return re.sub(r"[\W_]+", " ", t).strip()


@dataclass
class EgressGuard:
    article_body: str = ""
    extra_sensitive: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._article = _norm(self.article_body)

    def _leaks_article(self, value: str, allowed: str) -> str | None:
        v, ok = _norm(value), _norm(allowed)
        if len(v) < WINDOW or not self._article:
            return None
        for i in range(0, len(v) - WINDOW + 1, 4):
            chunk = v[i : i + WINDOW]
            if chunk in self._article and chunk not in ok:
                return chunk
        return None

    def _decoded_variants(self, value: str) -> list[str]:
        out = [value]
        for blob in re.findall(r"[A-Za-z0-9+/=_-]{16,}", value):
            try:
                out.append(base64.b64decode(blob + "=" * (-len(blob) % 4), altchars=b"-_").decode("utf-8", "ignore"))
            except (binascii.Error, ValueError):
                pass
            if re.fullmatch(r"[0-9a-fA-F]{24,}", blob):
                try:
                    out.append(bytes.fromhex(blob[: len(blob) // 2 * 2]).decode("utf-8", "ignore"))
                except ValueError:
                    pass
        return out

    def check_text(self, value: str, allowed_context: str = "") -> str | None:
        """Zwraca powód blokady albo None."""
        for variant in self._decoded_variants(value or ""):
            if SENSITIVE.search(variant):
                return "zawiera token-kanarek / dane oznaczone jako poufne"
            for s in self.extra_sensitive:
                if s and s.lower() in variant.lower():
                    return "zawiera dane oznaczone jako wrażliwe"
            leaked = self._leaks_article(variant, allowed_context)
            if leaked:
                return f"zawiera fragment artykułu spoza twierdzenia („{leaked[:30]}…”)"
        return None

    def check_url(self, url: str, allowed_context: str = "") -> str | None:
        if len(url) > MAX_URL:
            return f"URL dłuższy niż {MAX_URL} znaków"
        parts = urlsplit(url)
        for key, val in parse_qsl(parts.query, keep_blank_values=True):
            if len(val) > MAX_PARAM:
                return f"parametr „{key[:20]}” dłuższy niż {MAX_PARAM} znaków"
        return self.check_text(url, allowed_context) or self.check_text(parts.path + "?" + parts.query, allowed_context)
