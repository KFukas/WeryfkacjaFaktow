"""Oczyszczanie nieufnych stron (HTML/PDF/tekst/JSON) do samego tekstu + flagi manipulacji.

Kolejność dla HTML:
 1. parsowanie lxml (bez sieci, bez encji zewnętrznych), limit głębokości DOM,
 2. analiza (NIE kopiowanie do treści) kanałów pobocznych: komentarze, <meta>, <title>, JSON-LD,
    atrybuty alt/title/aria-label/…, <noscript>, <template>, iframe[srcdoc],
 3. usunięcie elementów aktywnych i niewidocznych (script/style/iframe/…, display:none, font-size:0,
    kolor tekstu = kolor tła, pozycjonowanie poza ekranem, hidden, aria-hidden…) — ich tekst też jest skanowany,
 4. ekstrakcja treści głównej (trafilatura, z fallbackiem),
 5. Unicode: odkodowanie Unicode Tags do analizy, usunięcie znaków zerowej szerokości/bidi, NFKC,
 6. detekcja wzorców injection, porównanie treści ukrytej z widoczną, neutralizacja znaczników ról,
 7. przycięcie do N znaków.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from typing import Any

from lxml import etree, html

from mcp_servers.web_sandbox import injection, unicode_tools

ACTIVE_TAGS = {"script", "style", "noscript", "iframe", "frame", "frameset", "template", "object", "embed",
               "applet", "svg", "math", "canvas", "form", "input", "button", "select", "textarea", "link",
               "meta", "base", "audio", "video", "source", "track", "dialog", "portal"}
ANALYZED_ATTRS = ("alt", "title", "aria-label", "aria-description", "aria-roledescription", "placeholder",
                  "value", "label", "summary", "data-instructions", "data-prompt")
MAX_DEPTH = 120
# URL-e wyglądające na kanał eksfiltracji: szablony do wypełnienia albo parametry nazwane jak dane redakcji.
_EXFIL_URL = re.compile(r"(\{\{|%7b%7b|\$\{|\[(article|claim|tresc|secret)|[?&](data|exfil|payload|secret|token|"
                        r"prompt|article|claim|tresc|leak|c|d)=[^&]{0,4}(\{|%7b|\[))", re.I)
MAX_INPUT_CHARS = 3_000_000
BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "section",
              "article", "header", "footer", "blockquote", "pre", "dd", "dt", "figcaption", "main", "aside"}

NAMED_COLORS = {"white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0), "green": (0, 128, 0),
                "blue": (0, 0, 255), "yellow": (255, 255, 0), "gray": (128, 128, 128), "grey": (128, 128, 128),
                "silver": (192, 192, 192), "whitesmoke": (245, 245, 245), "snow": (255, 250, 250),
                "ivory": (255, 255, 240), "ghostwhite": (248, 248, 255), "navy": (0, 0, 128)}


@dataclass
class SanitizeResult:
    title: str
    text: str
    injection_flags: list[dict]
    removed: dict[str, int]
    metadata: dict[str, Any]
    truncated: bool
    hidden_text: str = ""

    def envelope(self, url: str, final_url: str, fetched_at: str, raw: bytes, content_type: str) -> dict:
        return {
            "url": url,
            "final_url": final_url,
            "fetched_at": fetched_at,
            "content_sha256": hashlib.sha256(raw).hexdigest(),
            "content_type": content_type,
            "title": self.title,
            "text": self.text,
            "untrusted": True,
            "truncated": self.truncated,
            "injection_flags": self.injection_flags,
            "removed": self.removed,
            "metadata": self.metadata,
        }


@dataclass
class _State:
    removed: dict[str, int] = field(default_factory=lambda: {
        "scripts": 0, "styles": 0, "active_elements": 0, "hidden_elements": 0, "comments": 0, "attributes": 0,
        "zero_width_chars": 0, "bidi_chars": 0, "unicode_tags": 0, "deep_nodes": 0})
    flags: list[dict] = field(default_factory=list)
    hidden_chunks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    uni: unicode_tools.UnicodeReport = field(default_factory=unicode_tools.UnicodeReport)

    def scan(self, text: str, channel: str) -> list[dict]:
        cleaned = unicode_tools.clean(text, self.uni)
        found = injection.scan(cleaned, channel)
        self.flags += found
        return found


# --- CSS ------------------------------------------------------------------
def _parse_style(style: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for decl in style.split(";"):
        if ":" in decl:
            k, _, v = decl.partition(":")
            out[k.strip().lower()] = v.strip().lower().replace("!important", "").strip()
    return out


def _parse_color(value: str) -> tuple[int, int, int, float] | None:
    v = value.strip().lower()
    if not v:
        return None
    if v == "transparent":
        return (0, 0, 0, 0.0)
    if v in NAMED_COLORS:
        return (*NAMED_COLORS[v], 1.0)
    m = re.fullmatch(r"#([0-9a-f]{3,8})", v)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) in (6, 8):
            a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)
    m = re.fullmatch(r"rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)(?:[\s,/]+([\d.]+%?))?\s*\)", v)
    if m:
        a_raw = m.group(4)
        a = 1.0 if a_raw is None else (float(a_raw[:-1]) / 100 if a_raw.endswith("%") else float(a_raw))
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), a)
    return None


def _luminance(rgb: tuple[int, int, int]) -> float:
    def ch(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _px(value: str) -> float | None:
    m = re.match(r"^(-?[\d.]+)\s*(px|em|rem|pt|%|vw|vh)?$", value.strip())
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2) or "px"
    return num * {"px": 1, "em": 16, "rem": 16, "pt": 1.33, "%": 0.16, "vw": 10, "vh": 10}[unit]


def _hidden_by_style(decls: dict[str, str]) -> str | None:
    """Zwraca powód ukrycia albo None."""
    if decls.get("display") == "none":
        return "display:none"
    if decls.get("visibility") in ("hidden", "collapse"):
        return "visibility:hidden"
    op = decls.get("opacity")
    if op is not None:
        try:
            if float(op.rstrip("%")) / (100 if op.endswith("%") else 1) < 0.05:
                return "opacity:0"
        except ValueError:
            pass
    fs = decls.get("font-size")
    if fs is not None:
        size = _px(fs)
        if size is not None and size < 2:
            return "font-size≈0"
    for prop in ("left", "top", "right", "text-indent", "margin-left", "margin-top"):
        if prop in decls:
            v = _px(decls[prop])
            if v is not None and v <= -500:
                return f"{prop} poza ekranem"
    if "clip" in decls and re.search(r"rect\(\s*0", decls["clip"]):
        return "clip:rect(0)"
    if "clip-path" in decls and re.search(r"inset\(\s*(50|100)%|circle\(\s*0", decls["clip-path"]):
        return "clip-path"
    if "transform" in decls and re.search(r"scale\(\s*0(\.0+)?\s*[,)]", decls["transform"]):
        return "transform:scale(0)"
    for dim in ("width", "height", "max-height", "max-width"):
        if dim in decls and _px(decls[dim]) == 0 and decls.get("overflow", "") in ("hidden", "clip"):
            return f"{dim}:0 + overflow:hidden"
    col = _parse_color(decls.get("color", ""))
    if col is not None and col[3] < 0.05:
        return "color:transparent"
    return None


_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _stylesheet_hidden_selectors(doc) -> tuple[set[str], set[str], set[str], dict[str, dict[str, str]]]:
    """Proste reguły z <style>: .klasa / #id / tag ukrywające treść (+ deklaracje do analizy kolorów)."""
    classes, ids, tags = set(), set(), set()
    class_decls: dict[str, dict[str, str]] = {}
    for style_el in doc.iter("style"):
        css = re.sub(r"/\*.*?\*/", "", style_el.text or "", flags=re.S)
        for sel_group, body in _CSS_RULE.findall(css):
            decls = _parse_style(body)
            hidden = _hidden_by_style(decls)
            for sel in sel_group.split(","):
                sel = sel.strip()
                m = re.fullmatch(r"([a-z0-9]*)\.([\w-]+)", sel, re.I)
                if m:
                    class_decls.setdefault(m.group(2), {}).update(decls)
                    if hidden:
                        classes.add(m.group(2))
                    continue
                m = re.fullmatch(r"[a-z0-9]*#([\w-]+)", sel, re.I)
                if m:
                    class_decls.setdefault("#" + m.group(1), {}).update(decls)
                    if hidden:
                        ids.add(m.group(1))
                    continue
                if re.fullmatch(r"[a-z][a-z0-9]*", sel, re.I) and hidden and sel.lower() not in ("html", "body"):
                    tags.add(sel.lower())
    return classes, ids, tags, class_decls


def _effective_decls(el, class_decls: dict[str, dict[str, str]]) -> dict[str, str]:
    decls: dict[str, str] = {}
    for cls in (el.get("class") or "").split():
        decls.update(class_decls.get(cls, {}))
    if el.get("id"):
        decls.update(class_decls.get("#" + el.get("id"), {}))
    decls.update(_parse_style(el.get("style") or ""))
    if el.get("color"):  # <font color=…>
        decls.setdefault("color", el.get("color").lower())
    if el.get("bgcolor"):
        decls.setdefault("background-color", el.get("bgcolor").lower())
    return decls


def _background_of(decls: dict[str, str]) -> tuple[int, int, int] | None:
    for prop in ("background-color", "background"):
        if prop in decls:
            for token in re.split(r"\s+(?![^(]*\))", decls[prop]):
                col = _parse_color(token)
                if col is not None and col[3] > 0.5:
                    return col[:3]
    return None


# --- HTML -----------------------------------------------------------------
def _text_of(el) -> str:
    try:
        return re.sub(r"\s+", " ", el.text_content()).strip()
    except ValueError:
        return ""


def _limit_depth(root, state: _State) -> None:
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        for child in list(node):
            if depth + 1 >= MAX_DEPTH:
                state.removed["deep_nodes"] += sum(1 for _ in child.iter())
                node.remove(child)
            else:
                stack.append((child, depth + 1))


def _remove(el) -> None:
    """Usuwa element, zachowując tekst „ogonowy” (tail), który należy do rodzica i jest widoczny."""
    parent = el.getparent()
    if parent is None:
        return
    tail = el.tail
    prev = el.getprevious()
    parent.remove(el)
    if tail:
        if prev is not None:
            prev.tail = (prev.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail


def _visible_text(root) -> str:
    parts: list[str] = []

    def walk(node) -> None:  # iteracyjnie przez lxml.iter byłoby trudniej z tail — głębokość jest już ograniczona
        tag = node.tag if isinstance(node.tag, str) else ""
        if tag in BLOCK_TAGS:
            parts.append("\n")
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                parts.append(child.tail)
        if tag in BLOCK_TAGS:
            parts.append("\n")

    walk(root)
    text = "".join(parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return re.sub(r"\n{2,}", "\n\n", text).strip()


def _extract_main(cleaned_html: str, fallback: str) -> str:
    try:
        import trafilatura

        main = trafilatura.extract(cleaned_html, include_comments=False, include_tables=True, favor_recall=True,
                                   include_links=False, include_images=False, deduplicate=False)
    except Exception:  # noqa: BLE001 — ekstraktor nie może wywrócić sandboksa
        main = None
    if not main or len(main) < 0.4 * len(fallback):
        return fallback
    return main.strip()


def _jsonld_strings(obj: Any, out: list[str], depth: int = 0) -> None:
    if depth > 12 or len(out) > 500:
        return
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _jsonld_strings(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _jsonld_strings(v, out, depth + 1)


def _metadata_from_jsonld(obj: Any, meta: dict[str, Any]) -> None:
    items = obj if isinstance(obj, list) else [obj]
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("datePublished") and "published_at" not in meta:
            meta["published_at"] = str(it["datePublished"])[:40]
        author = it.get("author")
        if author and "author" not in meta:
            meta["author"] = (author.get("name") if isinstance(author, dict) else str(author))[:120]


def sanitize_html(raw_html: str, max_chars: int = 20_000) -> SanitizeResult:
    state = _State()
    if len(raw_html) > MAX_INPUT_CHARS:
        raw_html = raw_html[:MAX_INPUT_CHARS]
        state.flags.append({"type": "resource_limit", "severity": "low", "channel": "document",
                            "evidence": "dokument przycięty przed parsowaniem"})
    parser = html.HTMLParser(remove_blank_text=False, no_network=True, recover=True, huge_tree=False)
    try:
        doc = html.document_fromstring(raw_html or "<html></html>", parser=parser)
    except (etree.ParserError, ValueError):
        doc = html.document_fromstring("<html><body></body></html>")

    _limit_depth(doc, state)
    if state.removed["deep_nodes"]:
        state.flags.append({"type": "resource_limit", "severity": "medium", "channel": "document",
                            "evidence": f"DOM głębszy niż {MAX_DEPTH} — usunięto {state.removed['deep_nodes']} węzłów"})

    # 1) komentarze
    for c in list(doc.iter(etree.Comment)):
        state.scan(c.text or "", "html_comment")
        state.removed["comments"] += 1
        _remove(c)
    for pi in list(doc.iter(etree.ProcessingInstruction)):
        _remove(pi)

    # 2) <title>, <meta>, JSON-LD — tylko analiza
    title = ""
    title_el = doc.find(".//title")
    if title_el is not None:
        title = unicode_tools.clean(_text_of(title_el), state.uni)
        state.scan(title, "title")
    for meta in doc.iter("meta"):
        content = meta.get("content") or ""
        name = (meta.get("name") or meta.get("property") or meta.get("http-equiv") or "").lower()
        if name in ("article:published_time", "date", "dc.date", "pubdate", "og:published_time"):
            state.metadata.setdefault("published_at", content[:40])
        elif name in ("author", "dc.creator", "article:author"):
            state.metadata.setdefault("author", content[:120])
        elif name in ("og:site_name", "publisher", "dc.publisher"):
            state.metadata.setdefault("publisher_claimed", content[:120])
        elif name == "refresh":
            state.flags.append({"type": "fetch_instruction", "severity": "medium", "channel": "meta",
                                "evidence": f"meta refresh: {content[:100]}"})
        if content:
            state.scan(content, "meta")
    for script in doc.iter("script"):
        if (script.get("type") or "").lower() == "application/ld+json" and script.text:
            try:
                data = json.loads(script.text)
            except ValueError:
                state.scan(script.text, "json_ld")
                continue
            strings: list[str] = []
            _jsonld_strings(data, strings)
            state.scan("\n".join(strings), "json_ld")
            _metadata_from_jsonld(data, state.metadata)
    for t in doc.iter("time"):
        if t.get("datetime"):
            state.metadata.setdefault("published_at", t.get("datetime")[:40])
            break
    if re.search(r"metodologi|methodology|metadane|uwagi metodyczne", raw_html[:500_000], re.I):
        state.metadata["has_methodology"] = True

    # 3) atrybuty analizowane, potem usuwane (do treści i tak trafia tylko tekst)
    for el in doc.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in ANALYZED_ATTRS:
            val = el.get(attr)
            if val and len(val.strip()) > 3:
                state.scan(val, f"attr:{attr}")
        for attr, val in el.attrib.items():
            if attr.startswith("on"):
                state.removed["attributes"] += 1
            elif attr.startswith("data-") and len(val) > 40 and attr not in ANALYZED_ATTRS:
                state.scan(val, "attr:data")
        if el.tag == "iframe" and el.get("srcdoc"):
            state.scan(el.get("srcdoc"), "iframe_srcdoc")
        if el.tag in ("a", "img"):
            target = el.get("href") or el.get("src") or ""
            if _EXFIL_URL.search(target):
                state.flags.append({"type": "exfiltration", "severity": "medium", "channel": f"attr:{el.tag}",
                                    "evidence": f"podejrzany URL: {target[:120]}"})

    # 4) elementy aktywne
    hidden_classes, hidden_ids, hidden_tags, class_decls = _stylesheet_hidden_selectors(doc)
    for el in list(doc.iter(*ACTIVE_TAGS)):
        if el.getparent() is None:
            continue
        tag = el.tag
        text = _text_of(el)
        if tag in ("noscript", "template", "svg", "math", "form", "dialog") and text:
            state.scan(text, tag)
            if len(text) > 20:
                state.hidden_chunks.append(text)
        if tag == "script":
            state.removed["scripts"] += 1
        elif tag == "style":
            state.removed["styles"] += 1
        else:
            state.removed["active_elements"] += 1
        _remove(el)
    head = doc.find("head")
    if head is not None:
        _remove(head)

    # 5) elementy niewidoczne (style inline, arkusze, atrybuty, kolor tekstu = tło)
    body = doc.find("body") if doc.find("body") is not None else doc
    page_bg = _background_of(_effective_decls(body, class_decls)) or (255, 255, 255)
    stack: list[tuple[Any, tuple[int, int, int], tuple[int, int, int] | None]] = [(body, page_bg, None)]
    to_remove: list[tuple[Any, str]] = []
    while stack:
        node, bg, fg = stack.pop()
        for child in node:
            if not isinstance(child.tag, str):
                continue
            decls = _effective_decls(child, class_decls)
            reason = _hidden_by_style(decls)
            classes = set((child.get("class") or "").split())
            if reason is None and (classes & hidden_classes or child.get("id") in hidden_ids
                                   or child.tag in hidden_tags):
                reason = "reguła CSS z <style>"
            if reason is None and child.get("hidden") is not None:
                reason = "atrybut hidden"
            if reason is None and (child.get("aria-hidden") or "").lower() == "true":
                reason = "aria-hidden"
            if reason is None and (classes & {"sr-only", "visually-hidden", "screen-reader-text", "hidden",
                                              "d-none", "invisible"}):
                reason = f"klasa {sorted(classes & {'sr-only', 'visually-hidden', 'screen-reader-text', 'hidden', 'd-none', 'invisible'})[0]}"
            child_bg = _background_of(decls) or bg
            col = _parse_color(decls.get("color", ""))
            child_fg = col[:3] if col is not None and col[3] >= 0.05 else fg
            if reason is None and child_fg is not None and _contrast(child_fg, child_bg) < 1.25 and _text_of(child):
                reason = "kolor tekstu ≈ kolor tła"
            if reason:
                to_remove.append((child, reason))
            else:
                stack.append((child, child_bg, child_fg))
    for el, reason in to_remove:
        text = _text_of(el)
        state.removed["hidden_elements"] += 1
        if text:
            found = state.scan(text, "hidden")
            state.hidden_chunks.append(text)
            # Krótkie teksty interfejsu (sr-only, aria-hidden, menu) są normalne — liczymy je, ale nie flagujemy.
            if injection.has_instruction(found) or _is_prose(text):
                sev = "high" if injection.has_instruction(found) else "medium"
                state.flags.append({"type": "hidden_text", "severity": sev, "channel": "hidden",
                                    "evidence": f"[{reason}] {unicode_tools.clean(text)[:160]}"})
        _remove(el)

    # 6) widoczny tekst + treść główna
    fallback = _visible_text(body)
    main_el = body.find(".//article")
    if main_el is None:
        main_el = body.find(".//main")
    if main_el is not None and len(_text_of(main_el)) >= 0.3 * len(_text_of(body)):
        main = _visible_text(main_el)  # semantyczny kontener treści — zachowujemy podział na akapity
    elif fallback.strip():
        main = _extract_main(etree.tostring(body, encoding="unicode", method="html"), fallback)
    else:
        main = ""
    return _finalize(state, title, fallback, main, max_chars)


def _is_prose(text: str) -> bool:
    """Zdanie/akapit (a nie etykieta UI): ≥ 7 słów i znak końca zdania."""
    return len(text.split()) >= 7 and bool(re.search(r"[.!?:](\s|$)", text))


def _numbers(text: str, significant: bool = False) -> set[str]:
    out = set()
    for raw in re.findall(r"\d[\d \u00a0]*(?:[.,]\d+)?\s*%?", text):
        n = raw.replace(" ", "").replace("\u00a0", "").replace(",", ".").rstrip()
        digits = n.rstrip("%")
        if len(digits) < 2:
            continue
        if significant and not ("." in digits or n.endswith("%") or len(digits.replace(".", "")) >= 3):
            continue
        out.add(digits)
    return out


def _finalize(state: _State, title: str, visible: str, main: str, max_chars: int) -> SanitizeResult:
    uni = state.uni
    visible_clean = unicode_tools.clean(visible, uni)
    text = unicode_tools.clean(main, unicode_tools.UnicodeReport()) if main is not visible else visible_clean
    state.removed["zero_width_chars"] = uni.zero_width
    state.removed["bidi_chars"] = uni.bidi
    state.removed["unicode_tags"] = uni.tags

    # analiza widocznej treści (cała, nie tylko część główna)
    state.flags += injection.scan(visible_clean, "visible")
    if uni.tag_payload.strip():
        inner = injection.scan(uni.tag_payload, "unicode_tags")
        state.flags.append({"type": "unicode_smuggling", "severity": "high" if inner or len(uni.tag_payload) > 8
                            else "medium", "channel": "unicode_tags",
                            "evidence": f"ukryty tekst w Unicode Tags: {uni.tag_payload[:120]}"})
        state.flags += inner
    zw_ratio = uni.zero_width / max(1, len(visible))
    if uni.zero_width >= 40 or (uni.zero_width >= 8 and zw_ratio > 0.01) or uni.bidi_controls >= 2:
        state.flags.append({"type": "unicode_smuggling", "severity": "medium", "channel": "visible",
                            "evidence": f"{uni.zero_width} znaków zerowej szerokości, "
                                        f"{uni.bidi_controls} znaków sterujących kierunkiem tekstu"})
    mixed = unicode_tools.mixed_script_words(visible_clean + " " + title)
    if mixed:
        state.flags.append({"type": "homoglyph", "severity": "medium", "channel": "visible",
                            "evidence": "słowa z mieszanymi alfabetami: " + ", ".join(mixed[:5])})

    hidden = " ".join(state.hidden_chunks)
    prose = " ".join(c for c in state.hidden_chunks if _is_prose(c))
    if prose:
        new_numbers = _numbers(prose) - _numbers(visible_clean)
        if new_numbers:
            state.flags.append({"type": "hidden_visible_mismatch", "severity": "high", "channel": "hidden",
                                "evidence": "ukryta treść zawiera liczby nieobecne w widocznej: "
                                            + ", ".join(sorted(new_numbers)[:6])})

    text = injection.neutralize(text)
    title = injection.neutralize(title)[:300]
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars].rsplit(" ", 1)[0] + " […]"
    return SanitizeResult(title=title, text=text, injection_flags=injection.dedupe(state.flags),
                          removed=state.removed, metadata=state.metadata, truncated=truncated,
                          hidden_text=unicode_tools.clean(hidden)[:2000])


def sanitize_text(raw: str, max_chars: int = 20_000, channel: str = "visible") -> SanitizeResult:
    state = _State()
    return _finalize(state, "", raw, raw, max_chars)


def sanitize_json(raw: str, max_chars: int = 20_000) -> SanitizeResult:
    try:
        data = json.loads(raw)
    except ValueError:
        return sanitize_text(raw, max_chars)
    strings: list[str] = []
    _jsonld_strings(data, strings)
    return sanitize_text("\n".join(strings), max_chars)


# --- PDF ------------------------------------------------------------------
def sanitize_pdf(raw: bytes, max_chars: int = 20_000, max_pages: int = 50) -> SanitizeResult:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    state = _State()
    if re.search(rb"/(JavaScript|JS|Launch|EmbeddedFile|OpenAction|AA)\b", raw):
        state.flags.append({"type": "pdf_active_content", "severity": "medium", "channel": "pdf",
                            "evidence": "PDF zawiera akcje/JavaScript/załączniki — zignorowane (nie wykonujemy)"})
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        if reader.is_encrypted:
            raise PdfReadError("zaszyfrowany PDF")
    except Exception as exc:  # noqa: BLE001
        res = sanitize_text("", max_chars)
        res.injection_flags.append({"type": "parse_error", "severity": "low", "channel": "pdf",
                                    "evidence": f"nie można odczytać PDF: {type(exc).__name__}"})
        return res

    visible_parts: list[str] = []
    meta = reader.metadata or {}
    title = str(meta.get("/Title", "") or "")
    for key in ("/Title", "/Subject", "/Keywords", "/Author", "/Creator"):
        if meta.get(key):
            state.scan(str(meta.get(key)), "pdf_metadata")
    if meta.get("/Author"):
        state.metadata["author"] = str(meta.get("/Author"))[:120]
    if meta.get("/CreationDate"):
        state.metadata["published_at"] = str(meta.get("/CreationDate"))[:40]

    for page_no, page in enumerate(reader.pages):
        if page_no >= max_pages:
            state.flags.append({"type": "resource_limit", "severity": "low", "channel": "pdf",
                                "evidence": f"przetworzono tylko {max_pages} stron"})
            break
        gs = {"fill": (0.0, 0.0, 0.0), "mode": 0}
        stack: list[dict] = []
        vis: list[str] = []
        hid: list[str] = []

        def before(op, args, cm, tm, gs=gs, stack=stack):  # noqa: ANN001
            if op == b"q":
                stack.append(dict(gs))
            elif op == b"Q" and stack:
                gs.update(stack.pop())
            elif op == b"rg" and len(args) == 3:
                gs["fill"] = tuple(float(a) for a in args)
            elif op == b"g" and len(args) == 1:
                gs["fill"] = (float(args[0]),) * 3
            elif op == b"k" and len(args) == 4:
                c, m, y, k = (float(a) for a in args)
                gs["fill"] = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
            elif op == b"Tr" and args:
                gs["mode"] = int(args[0])

        def visit(text, cm, tm, font_dict, font_size, gs=gs, vis=vis, hid=hid):  # noqa: ANN001
            if not text:
                return
            scale = abs(tm[0] * cm[0]) if tm and cm else 1.0
            effective = (font_size or 0) * (scale or 1.0)
            white = min(gs["fill"]) > 0.95
            invisible = gs["mode"] == 3 or white or (0 < effective < 1.0)
            (hid if invisible else vis).append(text)

        try:
            page.extract_text(visitor_operand_before=before, visitor_text=visit)
        except Exception as exc:  # noqa: BLE001 — uszkodzona strona nie może wywrócić sandboksa
            state.flags.append({"type": "parse_error", "severity": "low", "channel": "pdf",
                                "evidence": f"str. {page_no + 1}: {type(exc).__name__}"})
            continue
        visible_parts.append("".join(vis))
        hidden_text = re.sub(r"\s+", " ", "".join(hid)).strip()
        if hidden_text:
            found = state.scan(hidden_text, "hidden")
            state.hidden_chunks.append(hidden_text)
            state.removed["hidden_elements"] += 1
            sev = "high" if injection.has_instruction(found) else ("medium" if len(hidden_text) >= 80 else "low")
            state.flags.append({"type": "hidden_text", "severity": sev, "channel": "pdf",
                                "evidence": f"[biały/niewidoczny tekst PDF, str. {page_no + 1}] {hidden_text[:160]}"})
    visible = re.sub(r"[ \t]+", " ", "\n".join(visible_parts)).strip()
    return _finalize(state, unicode_tools.clean(title), visible, visible, max_chars)


def sanitize(kind: str, body: bytes, encoding: str = "utf-8", max_chars: int = 20_000) -> SanitizeResult:
    if kind == "pdf":
        return sanitize_pdf(body, max_chars)
    text = body.decode(encoding or "utf-8", errors="replace")
    if kind == "html":
        if text.lstrip().startswith("%PDF"):
            return sanitize_pdf(body, max_chars)
        return sanitize_html(text, max_chars)
    if kind == "json":
        return sanitize_json(text, max_chars)
    return sanitize_text(text, max_chars)
