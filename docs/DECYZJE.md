# Rejestr decyzji architektonicznych (ADR-lite)

Każdy wpis: kontekst → decyzja → konsekwencje. Najnowsze na dole.

---

## D-001 — Jedno repozytorium Pythona, wiele pakietów
**Kontekst:** backend, dwa serwery MCP, orkiestrator i red-team dzielą modele danych i konfigurację.
**Decyzja:** jeden `pyproject.toml` z pakietami `backend`, `mcp_servers.web_sandbox`, `mcp_servers.newsroom`,
`orchestrator`, `redteam`. Frontend osobno w `frontend/` (npm).
**Konsekwencje:** prosta instalacja (`pip install -e .[dev]`). Izolację sandboksa zapewnia proces/kontener i
środowisko uruchomieniowe, a nie osobny pakiet — sandbox **nie importuje** `backend` ani `orchestrator`
(pilnuje tego test `tests/sandbox/test_isolation.py`).

## D-002 — `mcp` 2.x: `MCPServer` zamiast `FastMCP`
**Kontekst:** specyfikacja wymienia FastMCP. Aktualny oficjalny pakiet `mcp` (2.3) przemianował `FastMCP` na
`mcp.server.mcpserver.MCPServer` (moduł `mcp.server.fastmcp` celowo zgłasza błąd importu).
**Decyzja:** używamy oficjalnego `mcp>=2.3,<3` i klasy `MCPServer` (ten sam dekoratorowy styl `@server.tool()`),
klient: `mcp.Client` (stdio przez `StdioServerParameters` albo URL streamable HTTP).
**Konsekwencje:** brak przypinania do starej wersji; kod zgodny z bieżącą dokumentacją SDK.

## D-003 — Python 3.12 w venv mimo nowszego interpretera w systemie
**Kontekst:** na maszynie deweloperskiej domyślny jest Python 3.14; specyfikacja wymaga 3.12.
**Decyzja:** skrypty tworzą `.venv` przez `py -3.12` (Windows) / `python3.12` (Linux). CI używa 3.12.

## D-004 — Sprawdzanie adresu IP w chwili łączenia (własny backend httpcore)
**Kontekst:** walidacja „rozwiąż DNS → sprawdź → połącz” jest podatna na DNS rebinding (dwie różne odpowiedzi).
**Decyzja:** backend sieciowy httpcore (`GuardedBackend`) sam rozwiązuje nazwę, odrzuca odpowiedź, jeśli
**którykolwiek** adres jest niepubliczny, i łączy się z dokładnie sprawdzonym IP (TLS/SNI nadal z nazwą hosta).
Przekierowania obsługujemy ręcznie, każdy skok przechodzi pełną walidację. `trust_env=False` — proxy ze zmiennych
środowiskowych ominęłoby kontrolę adresów.
**Konsekwencje:** korzystamy z prywatnego pola `HTTPTransport._pool` (httpx 0.28) — przy aktualizacji httpx test
`test_connection_uses_validated_ip` wykryje regresję.

## D-005 — Tryb offline z fixture'ów jako domyślny
**Kontekst:** testy i CI muszą być deterministyczne, bez sieci i kosztów.
**Decyzja:** `SANDBOX_OFFLINE=1` (domyślnie) — wyszukiwanie, zbiory danych i strony pochodzą z
`mcp_servers/web_sandbox/fixtures/` (uproszczone kopie, oznaczone jako fixture; liczby zweryfikowane z prawdziwymi
API: GUS BDL 60270, NBP 001/A/NBP/2024, Eurostat tps00001). Wyjątki dla serwera red-team przez `SANDBOX_TEST_ALLOW`.
**Konsekwencje:** wyniki offline są powtarzalne; tryb online włącza się `SANDBOX_OFFLINE=0`.

## D-006 — Heurystyki injection strojone na prawdziwych stronach
**Kontekst:** pierwsza wersja dawała fałszywe alarmy na Wikipedii i gov.pl (tytuły linków „przejdź na stronę główną”,
teksty `sr-only`, długie query stringi, miękkie dywizy).
**Decyzja:** krótkie ukryte teksty interfejsu są usuwane i liczone, ale nie flagowane; „pobierz/odwiedź” wymaga URL;
porównanie ukryte↔widoczne tylko dla ukrytej prozy i liczb znaczących; próg znaków zerowej szerokości względny.
**Konsekwencje:** flagi zachowują sens jako kara w ocenie wiarygodności; FP mierzymy w `redteam/eval_agent.py`.

## D-007 — Model domyślny `claude-sonnet-5-5`, konfigurowalny
**Kontekst:** specyfikacja wskazuje `claude-sonnet-5-5` jako domyślny i `claude-opus-5-5` jako opcję.
**Decyzja:** `ANTHROPIC_MODEL=claude-sonnet-5-5` w `.env.example`; serwerowy fallback przy odmowie
(`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`) włączony domyślnie, wyłączany `ANTHROPIC_FALLBACKS=off`.
