# Architektura

System składa się z pięciu komponentów rozdzielonych według **strefy zaufania**. Zasada nadrzędna: kod, który dotyka
treści z internetu, nie ma dostępu do bazy redakcji ani sekretów, a model językowy, który czyta tę treść, nie ma
narzędzi zapisu.

## Komponenty

```mermaid
flowchart LR
    subgraph UI["Frontend (React, :5173 / :8080)"]
        FE["Panel redaktora<br/>adnotacje · źródła · audyt"]
    end
    subgraph TRUSTED["Strefa ZAUFANA"]
        API["Backend API<br/>FastAPI :8000"]
        ORCH["Orkiestrator agenta<br/>pipeline + bramka narzędzi"]
        NEWS["MCP newsroom<br/>(stdio)"]
        DB[("PostgreSQL / SQLite")]
        SKILL["Skill weryfikacja-faktow<br/>(prompty etapów)"]
    end
    subgraph UNTRUSTED["Strefa NIEUFNA (osobny proces / kontener)"]
        SB["MCP web-sandbox<br/>SSRF · sanitizer · injection · score"]
    end
    NET(("Internet:<br/>GUS BDL, Eurostat, NBP,<br/>KRS, dane.gov.pl,<br/>Wikipedia, strony"))
    LLM(("Claude API"))

    FE -- "REST + SSE" --> API
    API -- "wątek w tle" --> ORCH
    ORCH -- "MCP: zapis po walidacji" --> NEWS
    NEWS --> DB
    API --> DB
    ORCH -- "MCP: tylko odczyt" --> SB
    SB -- "HTTP(S) z ochroną SSRF" --> NET
    ORCH -- "structured outputs / tool use" --> LLM
    SKILL -. "prompty" .-> ORCH
```

| Komponent | Kod | Odpowiedzialność |
|---|---|---|
| Frontend | `frontend/` | widok adnotacji, panel boczny, panel redaktora, postęp (SSE), audyt; treść zewnętrzna tylko jako tekst |
| Backend API | `backend/` | REST, model danych (SQLAlchemy 2 + Alembic), walidacja domenowa (`services.py`), uruchamianie przebiegów |
| Orkiestrator | `orchestrator/` | pipeline etapów, bramka narzędzi (allowlisty, egress, pochodzenie URL, budżet), reguły werdyktu, audyt |
| MCP newsroom | `mcp_servers/newsroom/` | strefa zaufana: odczyt artykułów, zapis twierdzeń/źródeł/werdyktów/zdarzeń |
| MCP web-sandbox | `mcp_servers/web_sandbox/` | strefa nieufna: wyszukiwanie, dane strukturalne, pobieranie stron, sanitizer, deterministyczna ocena |
| Skill | `.claude/skills/weryfikacja-faktow/` | procedura i prompty (jedno źródło prawdy dla Claude Code i orkiestratora) |
| Red-team | `redteam/` | spreparowane strony, serwer testowy, eval agenta |

## Przepływ danych — weryfikacja jednego artykułu

```mermaid
sequenceDiagram
    autonumber
    participant R as Redaktor (UI)
    participant A as API
    participant O as Orkiestrator
    participant N as MCP newsroom
    participant M as Model (Claude)
    participant S as MCP web-sandbox
    R->>A: POST /api/articles/{id}/verify
    A->>O: przebieg w tle (AgentRun)
    O->>N: get_article
    O->>M: ETAP 1 ekstrakcja (bez narzędzi, JSON Schema)
    O->>N: save_claims (offsety walidowane)
    loop każde twierdzenie
        O->>M: ETAP 2 plan zapytań
        O->>M: ETAP 3 research (tylko 3 narzędzia odczytu)
        M->>O: tool_use: search_public_sources / query_dataset / fetch_url_sanitized
        O->>O: bramka: allowlista, pochodzenie URL, egress (kanarki, artykuł)
        O->>S: wywołanie MCP
        S-->>O: koperta {text oczyszczony, injection_flags, untrusted: true}
        O->>M: KWARANTANNA: <untrusted_source> → JSON (cytaty, stance, manipulacje)
        O->>O: weryfikacja cytatów (dosłowne fragmenty)
        O-->>M: tool_result = streszczenie z kwarantanny
        O->>S: score_source (deterministycznie, rubryka YAML)
        O->>M: ETAP 5 werdykt (bez narzędzi): relacje, korekta ±15, propozycja
        O->>O: korroboracja + reguły werdyktu (decydują) + reconcile
        O->>N: attach_source ×n, save_verdict (walidacja)
    end
    O->>N: log_agent_event (każdy krok: prompty, narzędzia, tokeny, koszt)
    A-->>R: SSE: postęp, werdykty na żywo
```

## Strefy zaufania

```mermaid
flowchart TB
    subgraph Z1["Zaufane: kod redakcji + baza"]
        direction LR
        A1["API / orkiestrator<br/>klucz API, DATABASE_URL"]
        A2["newsroom MCP"]
    end
    subgraph Z2["Półzaufane: model językowy"]
        B1["etapy bez narzędzi<br/>(structured outputs)"]
        B2["research: 3 narzędzia odczytu"]
        B3["kwarantanna: brak narzędzi"]
    end
    subgraph Z3["Nieufne: internet"]
        C1["web-sandbox<br/>bez sekretów, bez bazy,<br/>read-only FS, limity CPU/RAM"]
        C2["strony WWW, snippety API"]
    end
    Z1 -- "decyduje o zapisie<br/>(reguły deterministyczne)" --> Z2
    Z2 -- "żądania przez bramkę" --> Z3
    Z3 -- "dane w kopercie untrusted<br/>+ flagi" --> Z2
```

| Granica | Mechanizm |
|---|---|
| Internet → sandbox | SSRF (IP sprawdzane przy łączeniu), limity, allowlista Content-Type, sanitizer, detekcja injection |
| Sandbox → orkiestrator | koperta `untrusted: true`, flagi, escapowanie w `<untrusted_source>` |
| Treść → model | kwarantanna (osobne wywołanie bez narzędzi), schemat JSON, weryfikacja cytatów |
| Model → narzędzia | allowlista per etap i per aktor, pochodzenie URL (tylko wyniki wyszukiwania), egress guard, budżet |
| Model → baza | brak bezpośredniego dostępu; zapis przez kod po regułach werdyktu i walidacji `services.py` |
| Sandbox → baza/sekrety | osobny proces z minimalnym środowiskiem (`mcp_servers/launch.py`), w Dockerze osobna sieć bez bazy |

## Model danych

```mermaid
erDiagram
    ARTICLE ||--o{ CLAIM : zawiera
    CLAIM ||--o{ CLAIM_SOURCE : "ma źródła"
    SOURCE ||--o{ CLAIM_SOURCE : "cytowane w"
    CLAIM ||--o{ EDITOR_DECISION : "decyzje redaktora"
    ARTICLE ||--o{ AGENT_RUN : przebiegi
    AGENT_RUN ||--o{ AGENT_EVENT : audyt
    ARTICLE { int id string title text body string author string status }
    CLAIM { int id int start_offset int end_offset string category string verdict float confidence text rationale json verdict_details }
    SOURCE { int id text url text final_url string publisher string source_type string content_sha256 int credibility_score json credibility_breakdown json injection_flags }
    CLAIM_SOURCE { string relation text quote bool quote_verified }
    EDITOR_DECISION { string editor string override_verdict string previous_verdict text note }
    AGENT_RUN { string id string status string model int tool_calls float cost_usd json progress }
    AGENT_EVENT { string stage string type string name json payload int duration_ms int input_tokens float cost_usd }
```

`Claim.effective_verdict` = ostatnia decyzja redaktora albo werdykt agenta (redaktor ma ostatnie słowo; historia
decyzji zachowana z `previous_verdict`).

## Uruchomienie: procesy i transporty
| Tryb | Sandbox | Newsroom | Baza |
|---|---|---|---|
| Lokalnie (`scripts/start.*`) | proces potomny stdio z minimalnym env | proces potomny stdio | SQLite `data/kurier.db` |
| Docker | kontener `mcp-web-sandbox` (streamable HTTP, sieć `sandbox` + `egress`) | proces stdio w kontenerze `api` | PostgreSQL (sieć `trusted`) |
| Claude Code | `.mcp.json` → `scripts/run_mcp.py web-sandbox` | `.mcp.json` → `scripts/run_mcp.py newsroom` | jak lokalnie |
| Testy | w procesie (`inproc`) albo stdio | w procesie | SQLite w katalogu tymczasowym |

Decyzje projektowe i ich uzasadnienia: [DECYZJE.md](DECYZJE.md).
