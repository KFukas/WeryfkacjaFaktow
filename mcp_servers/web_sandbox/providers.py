"""Klienci publicznych źródeł danych (oficjalne API) + tryb offline z fixture'ów.

Każde zapytanie sieciowe przechodzi przez `netguard.safe_fetch` (te same zabezpieczenia SSRF co strony),
a hosty API są stałe w kodzie — model nie może podać własnego adresu API.
Dostawcy: Wikipedia, Wikidata, GUS BDL, Eurostat, NBP, KRS, dane.gov.pl (+ indeks dodatkowy dla testów red-team).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from mcp_servers.web_sandbox import sanitizer
from mcp_servers.web_sandbox.netguard import FetchError, safe_fetch
from mcp_servers.web_sandbox.settings import PACKAGE_DIR, SandboxSettings
from mcp_servers.web_sandbox.unicode_tools import skeleton

FIXTURES = PACKAGE_DIR / "fixtures"

PROVIDERS = {
    "wikipedia": {"types": {"encyclopedia"}, "publisher": "Wikipedia"},
    "wikidata": {"types": {"encyclopedia"}, "publisher": "Wikidata"},
    "gus_bdl": {"types": {"official_statistics"}, "publisher": "GUS — Bank Danych Lokalnych"},
    "gus": {"types": {"official_statistics"}, "publisher": "Główny Urząd Statystyczny"},
    "eurostat": {"types": {"official_statistics"}, "publisher": "Eurostat"},
    "nbp": {"types": {"official_statistics"}, "publisher": "Narodowy Bank Polski"},
    "krs": {"types": {"public_register"}, "publisher": "Krajowy Rejestr Sądowy"},
    "dane_gov": {"types": {"primary_data"}, "publisher": "dane.gov.pl"},
    "gov_pl": {"types": {"government"}, "publisher": "gov.pl"},
    "nobelprize": {"types": {"scientific"}, "publisher": "Fundacja Nobla"},
}
STOP = {"oraz", "ktory", "ktora", "ktore", "wedlug", "roku", "jest", "byla", "bylo", "przez", "jako", "tego",
        "takze", "sobie", "ich", "jego", "with", "that", "this", "from", "the", "and", "dla", "nad", "pod"}


def _tokens(text: str) -> set[str]:
    """Tokeny do dopasowań offline: szkielet bez diakrytyków, rdzeń = pierwsze 5 znaków (polska fleksja)."""
    words = re.findall(r"[a-z0-9]{3,}", skeleton(text))
    return {w[:5] for w in words if w not in STOP}


_JSON_CACHE: dict[str, Any] = {}


def _load_json(path: Path) -> Any:
    key = str(path)
    if key not in _JSON_CACHE:
        _JSON_CACHE[key] = json.loads(path.read_text(encoding="utf-8"))
    return _JSON_CACHE[key]


@dataclass
class Providers:
    settings: SandboxSettings

    # ---------------------------------------------------------------- utils
    def _get_json(self, url: str) -> Any:
        res = safe_fetch(url, self.settings, accept={"json"})
        return json.loads(res.body.decode(res.encoding or "utf-8", errors="replace"))

    def _index(self) -> list[dict]:
        docs = list(_load_json(FIXTURES / "search_index.json"))
        if self.settings.extra_index:
            p = Path(self.settings.extra_index)
            if p.is_file():
                docs += json.loads(p.read_text(encoding="utf-8"))
        return docs

    @staticmethod
    def _clean_snippet(text: str) -> tuple[str, list[dict]]:
        text = re.sub(r"<[^>]+>", "", text or "")
        res = sanitizer.sanitize_text(text, max_chars=500)
        return res.text, res.injection_flags

    # --------------------------------------------------------------- search
    def search(self, query: str, source_types: list[str] | None, lang: str, limit: int) -> dict:
        wanted = set(source_types or [])
        providers = [p for p, info in PROVIDERS.items() if not wanted or info["types"] & wanted]
        if self.settings.offline:
            results = self._search_offline(query, providers, limit)
            return {"query": query, "mode": "offline", "results": results, "errors": []}
        results, errors = [], []
        for name in providers:
            fn = getattr(self, f"_search_{name}", None)
            if fn is None:
                continue
            try:
                results += fn(query, lang, limit)
            except (FetchError, ValueError, KeyError, TypeError) as exc:
                errors.append({"provider": name, "error": getattr(exc, "code", type(exc).__name__)})
        results += self._search_offline(query, ["redteam"], limit, only_extra=True)
        return {"query": query, "mode": "online", "results": results[: max(limit, 1) * 2], "errors": errors}

    def _search_offline(self, query: str, providers: list[str], limit: int, only_extra: bool = False) -> list[dict]:
        q = _tokens(query)
        if not q:
            return []
        scored: list[tuple[float, dict]] = []
        for doc in self._index():
            if only_extra and doc.get("provider") != "redteam":
                continue
            if not only_extra and doc.get("provider") not in providers and doc.get("provider") != "redteam":
                continue
            dt = _tokens(" ".join([doc.get("title", ""), doc.get("snippet", ""), " ".join(doc.get("keywords", []))]))
            overlap = len(q & dt)
            if overlap >= max(1, min(2, len(q) // 3)):
                scored.append((overlap / len(q), doc))
        scored.sort(key=lambda t: -t[0])
        out = []
        for rel, doc in scored[:limit]:
            snippet, flags = self._clean_snippet(doc.get("snippet", ""))
            item = {"provider": doc["provider"], "title": doc.get("title", ""), "url": doc["url"],
                    "snippet": snippet, "publisher": doc.get("publisher", ""),
                    "published_at": doc.get("published_at"), "relevance": round(rel, 3),
                    "snippet_flags": flags, "untrusted": True}
            if doc.get("dataset"):
                item["dataset"] = doc["dataset"]
            out.append(item)
        return out

    def _search_wikipedia(self, query: str, lang: str, limit: int) -> list[dict]:
        lang = lang if lang in ("pl", "en") else "pl"
        params = urlencode({"action": "query", "list": "search", "srsearch": query, "format": "json",
                            "srlimit": min(limit, 5), "utf8": 1})
        data = self._get_json(f"https://{lang}.wikipedia.org/w/api.php?{params}")
        out = []
        for hit in data.get("query", {}).get("search", []):
            snippet, flags = self._clean_snippet(hit.get("snippet", ""))
            title = str(hit.get("title", ""))
            out.append({"provider": "wikipedia", "title": title,
                        "url": f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
                        "snippet": snippet, "publisher": "Wikipedia", "published_at": hit.get("timestamp"),
                        "snippet_flags": flags, "untrusted": True})
        return out

    def _search_wikidata(self, query: str, lang: str, limit: int) -> list[dict]:
        params = urlencode({"action": "wbsearchentities", "search": query[:100], "language": lang, "format": "json",
                            "limit": min(limit, 3)})
        data = self._get_json(f"https://www.wikidata.org/w/api.php?{params}")
        out = []
        for hit in data.get("search", []):
            snippet, flags = self._clean_snippet(hit.get("description", ""))
            qid = str(hit.get("id", ""))
            if not re.fullmatch(r"Q\d+", qid):
                continue
            out.append({"provider": "wikidata", "title": hit.get("label", qid),
                        "url": f"https://www.wikidata.org/wiki/{qid}", "snippet": snippet, "publisher": "Wikidata",
                        "snippet_flags": flags, "untrusted": True,
                        "dataset": {"provider": "wikidata", "dataset_id": qid, "params": {}}})
        return out

    def _search_gus_bdl(self, query: str, lang: str, limit: int) -> list[dict]:
        params = urlencode({"name": query[:100], "format": "json", "page-size": min(limit, 5), "lang": lang})
        data = self._get_json(f"https://bdl.stat.gov.pl/api/v1/variables/search?{params}")
        out = []
        for var in data.get("results", []):
            vid = str(var.get("id", ""))
            if not vid.isdigit():
                continue
            label = " / ".join(str(var.get(k, "")) for k in ("n1", "n2", "n3") if var.get(k))
            snippet, flags = self._clean_snippet(label)
            out.append({"provider": "gus_bdl", "title": snippet or f"Zmienna {vid}",
                        "url": f"https://bdl.stat.gov.pl/api/v1/variables/{vid}", "snippet": snippet,
                        "publisher": "GUS — Bank Danych Lokalnych", "snippet_flags": flags, "untrusted": True,
                        "dataset": {"provider": "gus_bdl", "dataset_id": vid, "params": {"unit-level": "0"}}})
        return out

    def _search_dane_gov(self, query: str, lang: str, limit: int) -> list[dict]:
        params = urlencode({"q": query[:100], "per_page": min(limit, 5), "model[terms]": "dataset"})
        data = self._get_json(f"https://api.dane.gov.pl/1.4/search?{params}")
        out = []
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            did = str(item.get("id", ""))
            if not did.isdigit():
                continue
            snippet, flags = self._clean_snippet(str(attrs.get("notes", ""))[:400])
            out.append({"provider": "dane_gov", "title": str(attrs.get("title", ""))[:200],
                        "url": f"https://dane.gov.pl/pl/dataset/{did}", "snippet": snippet,
                        "publisher": "dane.gov.pl", "published_at": attrs.get("modified"),
                        "snippet_flags": flags, "untrusted": True,
                        "dataset": {"provider": "dane_gov", "dataset_id": did, "params": {}}})
        return out

    def _search_eurostat(self, query: str, lang: str, limit: int) -> list[dict]:
        # Eurostat nie ma wyszukiwarki pełnotekstowej w API — korzystamy ze stałego katalogu zbiorów.
        q = _tokens(query)
        out = []
        for ds in _load_json(FIXTURES / "eurostat_catalog.json"):
            if q & _tokens(ds["title"] + " " + " ".join(ds["keywords"])):
                out.append({"provider": "eurostat", "title": ds["title"],
                            "url": f"https://ec.europa.eu/eurostat/databrowser/view/{ds['code']}/default/table",
                            "snippet": ds["title"], "publisher": "Eurostat", "snippet_flags": [], "untrusted": True,
                            "dataset": {"provider": "eurostat", "dataset_id": ds["code"], "params": ds["params"]}})
        return out[:limit]

    # -------------------------------------------------------------- datasets
    def query(self, provider: str, dataset_id: str, params: dict[str, Any] | None) -> dict:
        params = {str(k): str(v) for k, v in (params or {}).items()}
        if provider not in PROVIDERS:
            raise FetchError("unknown_provider", f"nieznany dostawca „{provider}”")
        if not re.fullmatch(r"[A-Za-z0-9_\-./]{1,80}", dataset_id or ""):
            raise FetchError("invalid_dataset", "nieprawidłowy identyfikator zbioru")
        for k, v in params.items():
            if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", k) or not re.fullmatch(r"[\w\-.:, ]{0,80}", v):
                raise FetchError("invalid_params", f"nieprawidłowy parametr {k}")
        if self.settings.offline:
            data = _load_json(FIXTURES / "datasets.json").get(f"{provider}:{dataset_id}")
            if data is None:
                raise FetchError("not_found", f"brak zbioru {provider}:{dataset_id} w danych offline")
            result = dict(data)
        else:
            fn = getattr(self, f"_query_{provider}", None)
            if fn is None:
                raise FetchError("unsupported", f"dostawca {provider} nie obsługuje zapytań strukturalnych")
            result = fn(dataset_id, params)
        rendered = sanitizer.sanitize_text(result.get("text", ""), max_chars=self.settings.max_text_chars)
        result.update({"provider": provider, "dataset_id": dataset_id, "params": params, "text": rendered.text,
                       "injection_flags": rendered.injection_flags, "untrusted": True,
                       "mode": "offline" if self.settings.offline else "online"})
        return result

    def _query_gus_bdl(self, dataset_id: str, params: dict[str, str]) -> dict:
        if not dataset_id.isdigit():
            raise FetchError("invalid_dataset", "identyfikator zmiennej BDL musi być liczbą")
        qp = {"format": "json", "unit-level": params.get("unit-level", "0")}
        if params.get("year"):
            qp["year"] = params["year"]
        url = f"https://bdl.stat.gov.pl/api/v1/data/by-variable/{dataset_id}?{urlencode(qp)}"
        data = self._get_json(url)
        rows = []
        for res in data.get("results", [])[:3]:
            vals = ", ".join(f"{v.get('year')}: {v.get('val')}" for v in res.get("values", [])[-10:])
            rows.append(f"{res.get('name', '')}: {vals}")
        return {"text": f"GUS BDL — zmienna {dataset_id}\n" + "\n".join(rows), "data": data.get("results", [])[:3],
                "metadata": {"publisher": "Główny Urząd Statystyczny", "url": url, "title": f"BDL zmienna {dataset_id}",
                             "published_at": data.get("lastUpdate"), "structured_api": True}}

    def _query_eurostat(self, dataset_id: str, params: dict[str, str]) -> dict:
        qp = {"format": "JSON", "lang": "EN", **params}
        url = f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{quote(dataset_id)}?{urlencode(qp)}"
        data = self._get_json(url)
        values = data.get("value", {})
        dims = data.get("id", [])
        sizes = data.get("size", [])
        labels = []
        for d in dims:
            cat = data["dimension"][d]["category"]
            idx = sorted(cat["index"].items(), key=lambda kv: kv[1])
            labels.append([cat.get("label", {}).get(k, k) for k, _ in idx])
        rows = []
        for key, val in list(values.items())[:30]:
            i, combo = int(key), []
            for size, lab in zip(reversed(sizes), reversed(labels), strict=False):
                combo.append(lab[i % size])
                i //= size
            rows.append(" / ".join(reversed(combo)) + f": {val}")
        return {"text": f"Eurostat {dataset_id} — {data.get('label', '')}\n" + "\n".join(rows),
                "data": {"rows": rows}, "metadata": {"publisher": "Eurostat", "url": url, "title": data.get("label", ""),
                                                     "published_at": data.get("updated"), "structured_api": True}}

    def _query_nbp(self, dataset_id: str, params: dict[str, str]) -> dict:
        if dataset_id == "exchangerates":
            table, code = params.get("table", "A"), params.get("code", "EUR")
            date = params.get("date", "")
            url = f"https://api.nbp.pl/api/exchangerates/rates/{table}/{code}/{date + '/' if date else ''}?format=json"
            data = self._get_json(url)
            rates = data.get("rates", [])
            text = "\n".join(f"{data.get('currency', code)} ({code}) {r.get('effectiveDate')}: {r.get('mid')} PLN "
                             f"(tabela {r.get('no')})" for r in rates)
        elif dataset_id == "cenyzlota":
            date = params.get("date", "")
            url = f"https://api.nbp.pl/api/cenyzlota/{date + '/' if date else ''}?format=json"
            data = self._get_json(url)
            text = "\n".join(f"Cena 1 g złota {r.get('data')}: {r.get('cena')} PLN" for r in data)
        else:
            raise FetchError("invalid_dataset", "NBP: obsługiwane zbiory to exchangerates i cenyzlota")
        return {"text": text, "data": data, "metadata": {"publisher": "Narodowy Bank Polski", "url": url,
                                                         "title": f"NBP {dataset_id}", "structured_api": True}}

    def _query_krs(self, dataset_id: str, params: dict[str, str]) -> dict:
        if not re.fullmatch(r"\d{10}", dataset_id):
            raise FetchError("invalid_dataset", "numer KRS musi mieć 10 cyfr")
        rejestr = params.get("rejestr", "P")
        url = f"https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/{dataset_id}?{urlencode({'rejestr': rejestr, 'format': 'json'})}"
        data = self._get_json(url)
        odpis = data.get("odpis", {})
        podmiot = odpis.get("dane", {}).get("dzial1", {}).get("danePodmiotu", {})
        text = (f"KRS {dataset_id}: {podmiot.get('nazwa', '')}; forma prawna: {podmiot.get('formaPrawna', '')}; "
                f"stan na: {odpis.get('naglowekA', {}).get('stanZDnia', '')}")
        return {"text": text, "data": {"danePodmiotu": podmiot}, "metadata": {
            "publisher": "Krajowy Rejestr Sądowy", "url": url, "title": f"Odpis KRS {dataset_id}",
            "published_at": odpis.get("naglowekA", {}).get("stanZDnia"), "structured_api": True}}

    def _query_wikidata(self, dataset_id: str, params: dict[str, str]) -> dict:
        if not re.fullmatch(r"Q\d+", dataset_id):
            raise FetchError("invalid_dataset", "identyfikator Wikidata ma postać Q123")
        url = f"https://www.wikidata.org/wiki/Special:EntityData/{dataset_id}.json"
        data = self._get_json(url)
        ent = data.get("entities", {}).get(dataset_id, {})
        label = ent.get("labels", {}).get("pl", ent.get("labels", {}).get("en", {})).get("value", dataset_id)
        desc = ent.get("descriptions", {}).get("pl", {}).get("value", "")
        props = params.get("properties", "")
        lines = [f"Wikidata {dataset_id}: {label} — {desc}"]
        for prop in [p for p in props.split(",") if re.fullmatch(r"P\d+", p.strip())][:10]:
            for claim in ent.get("claims", {}).get(prop.strip(), [])[:5]:
                val = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
                lines.append(f"{prop}: {json.dumps(val, ensure_ascii=False)[:200]}")
        return {"text": "\n".join(lines), "data": {"label": label}, "metadata": {
            "publisher": "Wikidata", "url": f"https://www.wikidata.org/wiki/{dataset_id}", "title": label,
            "structured_api": True}}

    def _query_dane_gov(self, dataset_id: str, params: dict[str, str]) -> dict:
        if not dataset_id.isdigit():
            raise FetchError("invalid_dataset", "identyfikator zbioru dane.gov.pl musi być liczbą")
        url = f"https://api.dane.gov.pl/1.4/datasets/{dataset_id}"
        data = self._get_json(url)
        attrs = data.get("data", {}).get("attributes", {})
        text = f"{attrs.get('title', '')}\n{attrs.get('notes', '')}"[:4000]
        return {"text": text, "data": {"title": attrs.get("title")}, "metadata": {
            "publisher": str(attrs.get("institution", {}).get("title", "dane.gov.pl")) if isinstance(
                attrs.get("institution"), dict) else "dane.gov.pl",
            "url": f"https://dane.gov.pl/pl/dataset/{dataset_id}", "title": attrs.get("title", ""),
            "published_at": attrs.get("modified"), "structured_api": True}}

    # ---------------------------------------------------------------- pages
    def offline_page(self, url: str) -> tuple[str, str] | None:
        """Zwraca (treść, content_type) strony z archiwum offline albo None."""
        for doc in self._index():
            if doc.get("url") == url and doc.get("page"):
                path = FIXTURES / "pages" / doc["page"]
                if path.is_file():
                    return path.read_text(encoding="utf-8"), doc.get("content_type", "text/html")
        return None
