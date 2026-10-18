# Serwery MCP

Projekt ma dwa własne serwery MCP (oficjalny pakiet `mcp` 2.x, klasa `MCPServer`) — celowo rozdzielone na strefę
**zaufaną** i **nieufną**.

| Serwer | Moduł | Strefa | Transport | Dostęp |
|---|---|---|---|---|
| `web-sandbox` | `mcp_servers.web_sandbox.server` | NIEUFNA | stdio (lokalnie, Claude Code) / streamable HTTP `:8765/mcp` (Docker) | internet (z ochroną SSRF); **brak** bazy, sekretów, plików projektu |
| `newsroom` | `mcp_servers.newsroom.server` | ZAUFANA | stdio | baza redakcji (`DATABASE_URL`) |

## Rejestracja
- **Claude Code:** `.mcp.json` w katalogu głównym (ścieżki względne, launcher `scripts/run_mcp.py` wybiera
  interpreter z `.venv` na Windows i Linux). Sprawdzenie: `/mcp` → oba serwery „connected”. Projekt włącza je przez
  `enabledMcpjsonServers` w `.claude/settings.json`.
- **Claude Desktop:** dodaj do `claude_desktop_config.json` (podmień ścieżkę):
  ```json
  {"mcpServers": {
    "web-sandbox": {"command": "python", "args": ["C:/Projekty/WeryfkacjaFaktow/scripts/run_mcp.py", "web-sandbox"],
                    "env": {"SANDBOX_OFFLINE": "1"}},
    "newsroom":    {"command": "python", "args": ["C:/Projekty/WeryfkacjaFaktow/scripts/run_mcp.py", "newsroom"]}
  }}
  ```
- **Orkiestrator:** `orchestrator/mcp_clients.py` (`mcp.Client` z `StdioServerParameters` albo URL).
- **Ręcznie:** `python scripts/run_mcp.py web-sandbox` (stdio) albo
  `python -m mcp_servers.web_sandbox.server --http --port 8765`.

Launcher przekazuje sandboksowi **wyłącznie** zmienne `SANDBOX_*` oraz systemowe minimum (`PATH`, `TEMP`…) — bez
`ANTHROPIC_API_KEY`, `DATABASE_URL`, tokenów (`mcp_servers/launch.py`, test `test_launcher_strips_secrets`).

---

## web-sandbox (strefa nieufna)

Każdy wynik ma `"untrusted": true`. Konfiguracja przez zmienne środowiskowe: `SANDBOX_OFFLINE` (1 = fixture'y),
`SANDBOX_TIMEOUT_S` (10), `SANDBOX_MAX_BYTES` (2 MB), `SANDBOX_MAX_TEXT_CHARS` (20 000), `SANDBOX_TEST_ALLOW`,
`SANDBOX_TEST_HOSTS`, `SANDBOX_EXTRA_INDEX` (tylko testy), `SANDBOX_HTTP_ALLOWED_HOSTS` (transport HTTP).

### `search_public_sources(query, source_types?, lang="pl", limit=8)`
Wyszukuje w publicznych źródłach. `source_types` filtruje dostawców: `official_statistics` (GUS, GUS BDL, Eurostat,
NBP), `public_register` (KRS), `primary_data` (dane.gov.pl), `government`, `scientific`, `encyclopedia` (Wikipedia,
Wikidata).
```json
// wejście
{"query": "stopa bezrobocia rejestrowanego grudzień 2023", "limit": 3}
// wyjście (skrót)
{"query": "…", "mode": "offline", "errors": [],
 "results": [{"provider": "gus", "title": "Bezrobocie rejestrowane — grudzień 2023",
              "url": "https://stat.gov.pl/obszary-tematyczne/rynek-pracy/bezrobocie-rejestrowane/",
              "snippet": "Stopa bezrobocia rejestrowanego w końcu grudnia 2023 r. wyniosła 5,1%.",
              "relevance": 1.0, "snippet_flags": [], "untrusted": true,
              "dataset": {"provider": "gus_bdl", "dataset_id": "60270", "params": {"year": "2023"}}}]}
```

### `query_dataset(provider, dataset_id, params?)`
Zapytanie strukturalne: `gus_bdl` (id zmiennej, `year`, `unit-level`), `eurostat` (kod zbioru, wymiary JSON-stat),
`nbp` (`exchangerates` z `table`, `code`, `date` albo `cenyzlota`), `krs` (10-cyfrowy numer, `rejestr` P/S),
`wikidata` (Q-id, `properties`), `dane_gov` (id zbioru). Hosty API są stałe w kodzie; parametry walidowane regexem.
```json
{"provider": "nbp", "dataset_id": "exchangerates", "params": {"table": "A", "code": "EUR", "date": "2024-01-02"}}
→ {"text": "euro (EUR) 2024-01-02: 4.3434 PLN (tabela 001/A/NBP/2024)",
   "data": {...}, "metadata": {"publisher": "Narodowy Bank Polski", "url": "https://api.nbp.pl/…",
   "published_at": "2024-01-02", "structured_api": true}, "injection_flags": [], "untrusted": true}
```

### `fetch_url_sanitized(url)`
Pobiera stronę i zwraca **wyłącznie oczyszczony tekst** w kopercie:
```json
{"url": "…", "final_url": "…", "fetched_at": "2026-10-18T08:21:03+00:00", "content_sha256": "9f2c…",
 "content_type": "text/html", "title": "Polska w NATO",
 "text": "Polska w NATO\n…\nPolska jest członkiem Sojuszu Północnoatlantyckiego (NATO) od 12 marca 1999 r.",
 "untrusted": true, "truncated": false,
 "injection_flags": [{"type": "hidden_text", "severity": "high", "channel": "hidden", "evidence": "…"}],
 "removed": {"scripts": 3, "styles": 1, "active_elements": 2, "hidden_elements": 5, "comments": 2,
             "attributes": 0, "zero_width_chars": 41, "bidi_chars": 0, "unicode_tags": 0, "deep_nodes": 0},
 "metadata": {"published_at": "2024-03-12", "author": "…", "has_methodology": true}}
```
Błędy: `{"error": "ssrf_blocked" | "too_large" | "timeout" | "unsupported_content_type" | "too_many_redirects" |
"http_error" | "dns_error" | "offline_unavailable", "message": "…"}`.

Zabezpieczenia: http/https, porty 80/443, IP sprawdzane w chwili łączenia (brak prywatnych, loopback, link-local,
CGNAT, metadanych chmury), ≤ 3 przekierowania z pełną walidacją, 10 s + deadline, 2 MB po dekompresji, Content-Type:
`text/html`, `application/xhtml+xml`, `text/plain`, `application/json`, `application/pdf`. Pełny opis sanitizera i
typów flag: [BEZPIECZENSTWO.md](BEZPIECZENSTWO.md).

Typy flag: `hidden_text`, `instruction_override`, `role_marker`, `persona_change`, `tool_instruction`,
`verdict_manipulation`, `exfiltration`, `fetch_instruction`, `social_engineering`, `self_declared_credibility`,
`secret_request`, `encoded_payload`, `unicode_smuggling`, `homoglyph`, `hidden_visible_mismatch`,
`pdf_active_content`, `resource_limit`, `cross_domain_redirect`, `parse_error`.

### `score_source(url, metadata?)`
Deterministyczna ocena 0–100 wg `config/credibility_rubric.yaml`. `metadata` może zawierać `injection_flags`,
`published_at`, `author`, `has_methodology`, `structured_api`, `claim_period`, `subject_is_publisher`,
`publisher_claimed` — wyłącznie obniżają lub dają drobne premie; **typ źródła wynika tylko z domeny**.
```json
{"url": "https://gus-oficjalny.info/dane", "metadata": {"injection_flags": [{"type": "self_declared_credibility", "severity": "medium"}]}}
→ {"score": 0, "source_type": "unknown", "publisher": "", "independence_group": "gus-oficjalny.info",
   "is_primary": false, "lookalike": "marka „gus” w domenie spoza listy oficjalnych",
   "breakdown": [{"criterion": "typ_zrodla", "points": 30, "detail": "źródło nieznane (gus-oficjalny.info)"},
                 {"criterion": "injection", "points": -8, "detail": "1 flag manipulacji (w tym 0 high)"},
                 {"criterion": "samozwancza_wiarygodnosc", "points": -15, "detail": "…"},
                 {"criterion": "domena_podrobka", "points": -40, "detail": "…"}]}
```

---

## newsroom (strefa zaufana)

Walidacja wspólna z REST API (`backend/services.py`). Błędy zwracane jako `{"error": "validation_error" | "not_found", "message": …}`.

| Narzędzie | Wejście | Wyjście / walidacja |
|---|---|---|
| `get_article(article_id)` | id | `{id, title, body, author, status, claims[]}` |
| `list_pending_articles()` | — | artykuły `draft` / `in_review` |
| `save_claims(article_id, claims[])` | `[{text, start_offset, end_offset, category}]` | tekst musi występować w artykule (offsety korygowane, gdy tekst jest jednoznaczny); idempotentne; artykuł → `in_review` |
| `attach_source(claim_id, source, relation, quote, quote_verified)` | `relation`: supports / contradicts / context | źródło deduplikowane po (url, sha256) |
| `save_verdict(claim_id, verdict, confidence, rationale, details?)` | `verdict`: potwierdzone / wątpliwe / fałszywe; `confidence` 0–1 | „potwierdzone” wymaga źródła `supports`, „fałszywe” — `contradicts` |
| `log_agent_event(run_id, event)` | `{stage, type, name, claim_id, payload, duration_ms, input_tokens, output_tokens, cost_usd}` | typy `progress` i `run_finished` aktualizują `AgentRun` |

Przykład:
```json
{"claim_id": 6, "verdict": "fałszywe", "confidence": 0.81,
 "rationale": "Wiarygodne źródło podaje inne dane niż twierdzenie ([S1]).",
 "details": {"rule_verdict": "fałszywe", "model_verdict": "fałszywe", "basis": ["S1"]}}
```

## Kto czego używa
| Narzędzie | Model (research) | Kod orkiestratora | Redaktor w Claude Code |
|---|---|---|---|
| `search_public_sources`, `query_dataset`, `fetch_url_sanitized` | ✔ (przez bramkę) | — | ✔ bez pytania |
| `score_source` | — | ✔ (etap assess) | ✔ |
| `get_article`, `list_pending_articles` | — | ✔ | ✔ |
| `save_claims`, `attach_source`, `save_verdict` | ✘ | ✔ (po regułach) | ✔ z potwierdzeniem |
| `log_agent_event` | ✘ | ✔ | — |
