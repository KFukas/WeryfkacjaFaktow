"""Heurystyczne wykrywanie prompt injection w nieufnej treści.

To NIE jest jedyna linia obrony (zob. docs/BEZPIECZENSTWO.md) — flagi obniżają ocenę wiarygodności
i są pokazywane redaktorowi, a granice bezpieczeństwa wymusza architektura (brak narzędzi zapisu dla treści
z sieci, allowlisty, strażnik ruchu wychodzącego, reguły werdyktu).

Wzorce działają na „szkielecie” tekstu (małe litery, bez diakrytyków, homoglify → łacina), więc
„IGNORUJ”, „іgnоruj” (cyrylica) i „ignoruj” dają to samo dopasowanie.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import re
from dataclasses import dataclass

from mcp_servers.web_sandbox.unicode_tools import skeleton

HIGH, MEDIUM, LOW = "high", "medium", "low"


@dataclass(frozen=True)
class Rule:
    type: str
    severity: str
    pattern: re.Pattern[str]


def _r(type_: str, severity: str, *alternatives: str) -> Rule:
    return Rule(type_, severity, re.compile("|".join(f"(?:{a})" for a in alternatives), re.IGNORECASE))


RULES: list[Rule] = [
    _r("instruction_override", HIGH,
       r"ignor\w*\s+(all\s+|wszystk\w*\s+)?(the\s+)?(previous|prior|above|earlier|poprzedni\w*|wczesniejsz\w*|powyzsz\w*)\s+(instructions?|instrukcj\w*|polecen\w*|prompt\w*|zasad\w*)",
       r"disregard\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|your)\s+\w+",
       r"forget\s+(all\s+|everything\s+|your\s+)(previous\s+)?(instructions?|rules|you were told)",
       r"zapomnij\s+(o\s+)?(wszystk\w*|poprzedni\w*|swoich|twoich)\s*\w*",
       r"(new|updated|nowe|zaktualizowane)\s+(system\s+)?(instructions?|instrukcje|polecenia)\s*:",
       r"override\s+(your|the)\s+(system|safety|instructions)",
       r"nie\s+stosuj\s+sie\s+do\s+(poprzednich|wczesniejszych|swoich)"),
    _r("role_marker", HIGH,
       r"<\|\s*im_(start|end)\s*\|>", r"<\|\s*(system|assistant|user|endoftext)\s*\|>",
       r"</?\s*untrusted_source\b", r"</?\s*(system|instructions?|admin)\s*>",
       r"\[/?\s*(inst|sys)\s*\]", r"<<\s*sys\s*>>",
       r"(^|\n)\s*(system|assistant|human|developer)\s*:\s*\S",
       r"#{2,}\s*(system|instruction|instrukcja)\b"),
    _r("persona_change", HIGH,
       r"you\s+are\s+now\s+(a|an|the|in)\b", r"from\s+now\s+on\s*,?\s+you", r"act\s+as\s+(a|an|the)\s+\w+",
       r"(jestes|bedziesz)\s+teraz\b", r"od\s+teraz\s+(jestes|bedziesz|masz)", r"wciel\s+sie\s+w",
       r"tryb\s+(dewelopera|administratora|bez\s+ograniczen)", r"developer\s+mode", r"\bjailbreak\b", r"\bdan\s+mode\b"),
    _r("tool_instruction", HIGH,
       r"\b(save_verdict|attach_source|save_claims|log_agent_event|fetch_url_sanitized|query_dataset|search_public_sources|score_source|get_article)\b",
       r"(call|invoke|use|run|execute)\s+(the\s+)?(tool|function)\b",
       r"(wywolaj|uzyj|uruchom)\s+(narzedzi\w*|funkcj\w*)", r"\btool_(use|call)\b", r"function_call"),
    _r("verdict_manipulation", HIGH,
       r"\b(oznacz|zaznacz|uznaj|ocen|sklasyfikuj|zakwalifikuj|potraktuj|przyjmij|oznaczyc|zaznaczyc|uznac|ocenic|sklasyfikowac|zakwalifikowac)(cie)?\s+(\w+\s+){0,4}jako\s+(prawd\w*|potwierdzon\w*|wiarygodn\w*|zweryfikowan\w*|falsz\w*|rzeteln\w*)",
       r"(mark|label|classify|rate|flag)\s+(this|it|the\s+claim|all\s+claims)\s+(\w+\s+){0,2}(as\s+)?(true|verified|confirmed|accurate|false|credible)",
       r"(werdykt|verdict)\s*[:=]\s*[\"']?(potwierdzone|prawda|true|verified|confirmed)",
       r"(credibility|wiarygodnosc\w*)\s*(score)?\s*[:=]\s*\d{2,3}",
       r"(ustaw|nadaj|set|give)\s+(\w+\s+){0,3}(score|ocen\w*|wiarygodnosc\w*|pewnosc\w*|confidence)\s*(na|to|=)?\s*\d"),
    _r("exfiltration", HIGH,
       r"!\[[^\]]*\]\(\s*https?://[^)\s]*\?[^)\s]*=",
       r"\[[^\]]*\]\(\s*https?://[^)\s]*\?[^)\s]*(\{|%7b|data|q|text|tresc|payload|secret|token)=",
       r"(send|post|upload|exfiltrat\w*|forward|leak)\s+(\w+\s+){0,4}(to|na|do)\s+(https?://|the\s+url|this\s+url|adres)",
       r"(wyslij|przeslij|wklej|dolacz|dopisz)\s+(\w+\s+){0,5}(na\s+adres|do\s+adresu|w\s+parametrze|do\s+url|w\s+url)",
       r"(append|include|add|put)\s+(\w+\s+){0,5}(to|in|into)\s+(the\s+)?(url|query\s+string|link|parameter)",
       r"\{\{\s*(article|artykul|claim|body|secret|api_key|system_prompt)\w*\s*\}\}"),
    _r("secret_request", MEDIUM,
       r"(podaj|ujawnij|wypisz|reveal|print|show|output|repeat)\s+(\w+\s+){0,3}(api[_\s-]?key|klucz\w*\s+api|system\s+prompt|prompt\w*\s+systemow\w*|instrukcj\w*\s+systemow\w*)"),
    _r("fetch_instruction", MEDIUM,
       r"(odwiedz|pobierz|otworz|wejdz\s+na|przejdz\s+(na|do)|sprawdz|zajrzyj\s+na|visit|fetch|open|browse\s+to|navigate\s+to|load|go\s+to|check)\s+(\w+\s+){0,4}(https?://|www\.)",
       r"(dalsze|wlasciwe|pelne|kolejne|prawdziwe)\s+instrukcj\w*\s+(znajdziesz|sa|pod|na)", r"(further|full|real|next)\s+instructions\s+(are\s+)?(at|on|in|can)"),
    _r("social_engineering", MEDIUM,
       r"redaktor\w*\s+naczeln\w*\s+(polecil|kazal|prosi|zdecydowal|zatwierdzil)",
       r"(pilne|natychmiast|bardzo\s+wazne|urgent|immediately|asap)\W+(\w+\W+){0,8}(oznacz|zmien|ustaw|zatwierdz|mark|change|set|approve|redaktor|editor)",
       r"(your|twoj\w*)\s+(boss|manager|szef\w*|przelozon\w*|developer\w*|tworc\w*)\s+(says|wants|told|kaze|chce|polecil)",
       r"(polecenie|decyzja)\s+(kierownictwa|zarzadu|redakcji)", r"on\s+behalf\s+of\s+(the\s+)?(editor|management|anthropic)",
       r"(anthropic|openai|administrator\w*\s+systemu)\s+(prosi|requires|wymaga|polecil|says)"),
    _r("self_declared_credibility", MEDIUM,
       r"(to|ta|ten|niniejsz\w*)\s+(jest\s+)?(oficjaln\w*|zweryfikowan\w*|certyfikowan\w*|w\s+pelni\s+wiarygodn\w*)\s+(zrodl\w*|stron\w*|serwis\w*)",
       r"(oficjaln\w*|jedyn\w*|zweryfikowan\w*)\s+(zrodl\w*|stron\w*|serwis\w*)\s+(gus|glownego\s+urzedu|nbp|rzadu|eurostatu|ministerstwa)",
       r"(this|the)\s+(is\s+(an?|the)\s+)?(official|verified|trusted|authoritative|certified)\s+(source|site|page|website)",
       r"(highest|maximum|najwyzsz\w*|maksymaln\w*)\s+(credibility|wiarygodnosc\w*|zaufani\w*)",
       r"(zrodlo|source)\s+(zweryfikowane|verified)\s+(przez|by)"),
]

INSTRUCTION_TYPES = {"instruction_override", "role_marker", "persona_change", "tool_instruction",
                     "verdict_manipulation", "exfiltration", "fetch_instruction", "secret_request"}

_B64 = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])")
_ROT13_HINT = re.compile(r"rot-?13|rot13", re.IGNORECASE)
_DECODE_HINT = re.compile(r"(zdekoduj|odkoduj|decode|base64|base-64)", re.IGNORECASE)


def _evidence(text: str, start: int, end: int, width: int = 60) -> str:
    s = max(0, start - width // 2)
    e = min(len(text), end + width // 2)
    return re.sub(r"\s+", " ", text[s:e]).strip()[:200]


def scan(text: str, channel: str = "visible", *, decode: bool = True) -> list[dict]:
    """Zwraca listę flag {type, severity, channel, evidence} dla jednego kanału treści."""
    if not text or not text.strip():
        return []
    sk = skeleton(text)
    flags: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rule in RULES:
        for m in rule.pattern.finditer(sk):
            key = (rule.type, channel)
            if key in seen:
                break
            seen.add(key)
            flags.append({"type": rule.type, "severity": rule.severity, "channel": channel,
                          "evidence": _evidence(sk, m.start(), m.end())})
            break
    if decode:
        flags += _scan_encoded(text, channel)
    return flags


def _printable_ratio(s: str) -> float:
    return sum(ch.isprintable() or ch in "\n\t" for ch in s) / max(1, len(s))


def _scan_encoded(text: str, channel: str) -> list[dict]:
    flags: list[dict] = []
    for m in _B64.finditer(text):
        blob = m.group(0)
        try:
            decoded = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if len(decoded) < 12 or _printable_ratio(decoded) < 0.9:
            continue
        inner = scan(decoded, channel, decode=False)
        if any(f["type"] in INSTRUCTION_TYPES for f in inner):
            flags.append({"type": "encoded_payload", "severity": HIGH, "channel": channel,
                          "evidence": f"base64 → {decoded[:120]}"})
        elif len(blob) >= 120 or _DECODE_HINT.search(text):
            flags.append({"type": "encoded_payload", "severity": MEDIUM, "channel": channel,
                          "evidence": f"długi blok base64 ({len(blob)} zn.)"})
        if len(flags) >= 3:
            break
    rot = codecs.decode(text, "rot13")
    inner = scan(rot, channel, decode=False)
    hits = [f for f in inner if f["type"] in INSTRUCTION_TYPES]
    if hits and (_ROT13_HINT.search(text) or not scan(text, channel, decode=False)):
        flags.append({"type": "encoded_payload", "severity": HIGH, "channel": channel,
                      "evidence": f"rot13 → {hits[0]['evidence'][:120]}"})
    return flags


def has_instruction(flags: list[dict]) -> bool:
    return any(f["type"] in INSTRUCTION_TYPES or f["type"] == "encoded_payload" for f in flags)


def neutralize(text: str) -> str:
    """Rozbraja znaczniki ról/koperty w tekście, żeby nie dało się „wyjść” z <untrusted_source>."""
    text = re.sub(r"<\|[^|>]{0,40}\|>", "[usunięty znacznik]", text)
    text = re.sub(r"</?\s*untrusted_source[^>]*>", "[usunięty znacznik]", text, flags=re.IGNORECASE)
    text = re.sub(r"</?\s*(system|instructions?|admin|assistant|user)\s*>", "[usunięty znacznik]", text,
                  flags=re.IGNORECASE)
    text = re.sub(r"\[/?\s*(INST|SYS)\s*\]", "[usunięty znacznik]", text, flags=re.IGNORECASE)
    return text


def dedupe(flags: list[dict], limit: int = 40) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for f in flags:
        key = (f["type"], f.get("channel", ""), f.get("evidence", "")[:60])
        if key not in seen:
            seen.add(key)
            out.append(f)
    order = {HIGH: 0, MEDIUM: 1, LOW: 2}
    out.sort(key=lambda f: order.get(f["severity"], 3))
    return out[:limit]
