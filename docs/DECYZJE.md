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

## D-008 — Pipeline sterowany kodem; pętla narzędzi modelu tylko w etapie research
**Kontekst:** agent z pełnym dostępem do narzędzi zapisu mógłby zostać nakłoniony przez treść strony do zapisu werdyktu.
**Decyzja:** etapy są sekwencją sterowaną kodem; model w etapie research ma wyłącznie trzy narzędzia odczytu strefy
nieufnej, pozostałe etapy działają bez narzędzi (structured outputs). Zapis do bazy robi kod po walidacji regułami.
**Konsekwencje:** mniejsza „autonomia” agenta, ale granica bezpieczeństwa nie zależy od posłuszeństwa modelu.

## D-009 — Kwarantanna (dual-LLM) i weryfikacja cytatów
**Decyzja:** każde pobrane źródło trafia do osobnego wywołania modelu bez narzędzi (może to być tańszy model —
`ANTHROPIC_QUARANTINE_MODEL`), które zwraca JSON wg schematu. Model główny widzi tylko ten JSON + flagi + ocenę.
Cytaty, które nie są dosłownym fragmentem tekstu źródła, są odrzucane; relacja supports/contradicts bez cytatu → context.

## D-010 — Minimalizacja danych w etapie research
**Decyzja:** model w etapie research widzi wyłącznie badane twierdzenie i plan — nie widzi treści artykułu ani notatek
redakcji. Strażnik ruchu wychodzącego dodatkowo blokuje fragmenty artykułu spoza twierdzenia i tokeny-kanarki.

## D-011 — Model „łatwowierny” w testach
**Decyzja:** `GullibleLLM` wykonuje każde polecenie ze źródeł (żąda narzędzi zapisu, odwiedza adresy z treści z
dopisanym artykułem, podbija ocenę, wymusza werdykt). Testy red-team offline mierzą, czy zabezpieczenia strukturalne
zatrzymują taki model — to dolna granica odporności niezależna od jakości prawdziwego LLM.

## D-012 — Frontend bez routera i biblioteki komponentów
**Decyzja:** prosty routing po `location.hash` i komponenty Tailwind zamiast react-router/UI-kitu — mniej zależności,
mniejsza powierzchnia ataku. Dostępność: werdykt kodowany kolorem, ikoną i wzorem podkreślenia; `aria-pressed`,
`aria-live` dla postępu. Treść zewnętrzna wyłącznie jako tekst; CSP wstrzykiwana tylko w buildzie produkcyjnym
(tryb dev Vite wymaga skryptów inline).

## D-013 — SSE zamiast WebSocket dla postępu
**Decyzja:** `GET /api/runs/{id}/stream` (Server-Sent Events) odpytuje bazę co 0,5 s i strumieniuje nowe zdarzenia
audytu. Jednokierunkowy kanał wystarcza, działa przez proxy nginx (`proxy_buffering off`) i nie wymaga stanu w pamięci API.

## D-014 — Treść główna z `<article>`/`<main>`, trafilatura jako fallback
**Kontekst:** trafilatura łączyła akapity w jedną linię, przez co cytaty sklejały tytuł, datę i zdanie.
**Decyzja:** jeśli strona ma semantyczny kontener z ≥ 30% tekstu, bierzemy jego widoczny tekst z podziałem na bloki;
trafilatura tylko dla stron bez takiego kontenera.

## D-015 — Wyjątki SSRF w testach po IP:port + mapowanie nazw tylko testowe
**Decyzja:** `SANDBOX_TEST_ALLOW` dopuszcza adres prywatny wyłącznie, gdy zgadza się **rozwiązany IP i port**;
nazwa hosta na liście zwalnia tylko z ograniczenia portu. `SANDBOX_TEST_HOSTS` (nazwa → IP) symuluje domeny-podróbki
i rebinding w testach. W produkcji obie zmienne są puste.

## D-016 — Docker: sandbox jako osobny kontener po streamable HTTP
**Decyzja:** w Dockerze `mcp-web-sandbox` to osobna usługa (read-only FS, UID 65534, `cap_drop: ALL`, 0,5 CPU / 512 MB,
sieci `sandbox` + `egress`, bez sieci bazy), a API łączy się z nim przez `http://mcp-web-sandbox:8765/mcp`. Serwer MCP
sprawdza nagłówek `Host`. Newsroom pozostaje procesem stdio w kontenerze API (strefa zaufana). Lokalnie Docker nie był
dostępny — stos jest budowany i testowany end-to-end w CI (job „Docker compose — build i test dymny”).

## D-017 — Model „łatwowierny” reaguje tylko na tryb rozkazujący
**Kontekst:** pierwsza wersja reagowała na słowo „oznacza” w zwykłym zdaniu GUS i „potwierdzała” twierdzenie
przyczynowe — to ujawniło ryzyko szczątkowe (błąd semantyczny modelu na wiarygodnym źródle), opisane w
`docs/BEZPIECZENSTWO.md`. Dla czytelności evalu wskazówki modelu `gullible` dopasowujemy z granicami słów.
