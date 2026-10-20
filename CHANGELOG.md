# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/), wersjonowanie: [SemVer](https://semver.org/lang/pl/).

## [Unreleased]
- `URUCHOM.bat` w głównym folderze: start całego projektu dwuklikiem (instalacja przy pierwszym uruchomieniu, build
  panelu, API + panel, otwarcie przeglądarki); automatyczny wybór wolnych portów (panel 8080, API 8010 — port 8000
  zostawiony innym projektom).
- `ZATRZYMAJ.bat`: zatrzymuje wyłącznie procesy tego projektu.
- Panel: znaczek statusu artykułu i przycisk „✔ Oznacz jako zweryfikowany” / „Cofnij zatwierdzenie” w widoku artykułu
  **i** na liście artykułów; przycisk nieaktywny (z podanym powodem), gdy brak twierdzeń lub trwa weryfikacja.
  Wcześniej przycisk znikał po zatwierdzeniu bez żadnej informacji i nie było go na liście.
- `scripts/serve-build.ps1`: build produkcyjny panelu na :8080 bez Dockera.

## [1.0.0] — 2026-10-18

### M0 – Szkielet
- Struktura repozytorium (pakiety `backend`, `mcp_servers`, `orchestrator`, `redteam`), `pyproject.toml`.
- README, CLAUDE.md, `.gitignore`, `.env.example`, licencja MIT.
- GitHub Actions (`ci.yml`): ruff + pytest, testy red-team offline, build frontendu (gdy istnieje).
- Szablony zgłoszeń (błąd, nowy przypadek red-team) i PR.
- Rejestr decyzji `docs/DECYZJE.md`.

### M1 – Backend + baza danych
- Modele SQLAlchemy 2: `Article`, `Claim`, `Source`, `ClaimSource`, `AgentRun`, `AgentEvent`, `EditorDecision`.
- Migracja Alembic `0001` (+ test braku dryfu modele↔migracje), SQLite (dev) / PostgreSQL (docker).
- Warstwa usług `backend/services.py` — wspólna walidacja dla REST i MCP (offsety twierdzeń, schemat werdyktu,
  wymagane źródło wspierające/przeczące).
- REST API: CRUD artykułów i twierdzeń, źródła, decyzje redaktora z historią, raport Markdown/JSON, audyt przebiegów.
- Seed: 4 fikcyjne artykuły po polsku z twierdzeniami prawdziwymi, fałszywymi i niejednoznacznymi.

### M2 – mcp-web-sandbox (strefa nieufna)
- Serwer MCP `web-sandbox` (stdio / streamable HTTP) z narzędziami `search_public_sources`, `query_dataset`,
  `fetch_url_sanitized`, `score_source`.
- `netguard`: tylko http/https i porty 80/443, blokada IP prywatnych/loopback/link-local/metadanych, sprawdzanie
  adresu **w chwili łączenia** (odporność na DNS rebinding), ręczne przekierowania (≤ 3), limity rozmiaru (po
  dekompresji), czasu i allowlista Content-Type; ignorowanie proxy ze środowiska.
- Sanitizer HTML/PDF/JSON: usuwanie elementów aktywnych i ukrytych (CSS inline i z `<style>`, kolor = tło, poza
  ekranem, `hidden`, `aria-hidden`…), analiza kanałów pobocznych (komentarze, meta, JSON-LD, atrybuty), Unicode
  (Tags, zero-width, bidi, NFKC, homoglify), base64/ROT13, neutralizacja znaczników ról, ekstrakcja treści głównej.
- Detektor prompt injection (PL/EN, odporny na homoglify i brak diakrytyków) + porównanie treści ukrytej z widoczną.
- Deterministyczna ocena wiarygodności `config/credibility_rubric.yaml` (typ z domeny, kary za flagi, domeny-podróbki).
- Klienci API: Wikipedia, Wikidata, GUS BDL, Eurostat, NBP, KRS, dane.gov.pl + tryb offline z fixture'ów.
- Testy: SSRF (20 wektorów), DNS rebinding, przekierowania, bomby rozmiaru, izolacja (brak importów strefy zaufanej,
  launcher bez sekretów), serwer MCP przez stdio; opcjonalne testy z prawdziwymi API (`RUN_NETWORK=1`).
- Strojenie fałszywych alarmów na prawdziwych stronach (Wikipedia, gov.pl, stat.gov.pl): 0 flag na stronach łagodnych.

### M3 – mcp-newsroom + orkiestrator
- Serwer MCP `newsroom` (strefa zaufana): `get_article`, `list_pending_articles`, `save_claims`, `attach_source`,
  `save_verdict`, `log_agent_event` — walidacja wspólna z REST (`backend/services.py`).
- Orkiestrator: ekstrakcja → plan → research → kwarantanna (dual-LLM) → ocena źródeł → werdykt → zapis.
- Bramka narzędzi: allowlisty per etap i per aktor (model dostaje wyłącznie narzędzia odczytu sandboksa w etapie
  research; zapis wykonuje kod), zasada pochodzenia URL-i, strażnik ruchu wychodzącego (kanarki, fragmenty artykułu,
  base64/hex), limity źródeł/pobrań, budżet wywołań i kosztu, pełny audyt (`AgentEvent`).
- Koperty `<untrusted_source>` z escapowaniem; cytaty weryfikowane jako dosłowne fragmenty źródła.
- Reguły werdyktu deterministyczne (`orchestrator/verdict_rules.py`) — przy niezgodności z modelem „wątpliwe”;
  korekta LLM ±15 (bez podwyżek dla źródeł z flagami), korroboracja niezależnych źródeł.
- Modele: `anthropic` (Claude, structured outputs, strict tool use, prompt caching, fallback przy odmowie),
  `mock` (deterministyczny offline), `gullible` (najgorszy przypadek do testów red-team).
- API: `POST /api/articles/{id}/verify`, `POST /api/claims/{id}/reverify`, SSE `GET /api/runs/{id}/stream`;
  idempotencja (klucz / trwający przebieg), CLI `python -m orchestrator.runner`.
- Skill `.claude/skills/weryfikacja-faktow/SKILL.md` jako źródło promptów (szkielet; uzupełniany w M4).
- Testy: werdykty 14 twierdzeń z seedów, audyt, ponowna weryfikacja, budżet, allowlisty, API + SSE, transport stdio.

### M4 – Skill Claude Code
- Skill `weryfikacja-faktow`: procedura krok po kroku, zasady bezpieczeństwa, sekcje promptów etapów (wczytywane
  przez orkiestrator), `references/` (rubryka, katalog źródeł publicznych, przykłady z próbą injection),
  `scripts/validate_verdicts.py`.
- `.mcp.json` (oba serwery przez launcher `scripts/run_mcp.py`, ścieżki względne, sandbox tylko ze zmiennymi `SANDBOX_*`).
- `.claude/settings.json`: allowlista testów/lint, odczyt MCP bez pytania, zapis do newsroom z potwierdzeniem,
  blokada `.env` i `WebFetch`.
- `docs/SKILL.md`; testy frontmattera, konfiguracji, startu serwerów jak w Claude Code i walidatora.

### M5 – Frontend
- React 18 + Vite + TypeScript + Tailwind + TanStack Query (`frontend/`).
- Widok artykułu z adnotacjami: kolor + ikona + wzór podkreślenia (ciągłe/przerywane/faliste/kropkowane) — czytelne
  bez rozróżniania kolorów; tryb jasny/ciemny.
- Panel boczny twierdzenia: werdykt, pewność, uzasadnienie, źródła z oceną rozpisaną na kryteria, cytaty, ostrzeżenia
  o wykrytym injection, decyzja redaktora z historią, ponowna weryfikacja twierdzenia.
- Panel redaktora: lista artykułów i statusów, dodawanie artykułu, uruchomienie weryfikacji, postęp na żywo (SSE),
  eksport raportu (Markdown/JSON), log agenta (audyt) z filtrem typów.
- Bezpieczeństwo UI: treść zewnętrzna tylko jako tekst (test pilnuje braku surowego HTML), linki wyłącznie http(s),
  CSP w buildzie produkcyjnym.
- Testy Vitest (segmentacja, adnotacje, XSS w cytatach/tytułach, panel) + e2e Playwright `scripts/ui_e2e.py`
  ze zrzutami do `docs/img/`.
- Sanitizer: treść główna z `<article>`/`<main>` z zachowaniem akapitów (trafilatura jako fallback).

### M6 – Red-team
- 31 spreparowanych stron (`redteam/pages/`, każda z `*.expected.yaml`): CSS, komentarze, meta, atrybuty, JSON-LD,
  Unicode Tags/zero-width, homoglify, base64/ROT13, znaczniki ról, polecenia narzędzi, eksfiltracja, domena-podróbka,
  SSRF (loopback, metadane, file://, rebinding), bomby zasobów, zły Content-Type, PDF z ukrytym tekstem, sprzeczność
  widoczne/ukryte, atak wielostopniowy, socjotechnika, iframe/noscript/template, bidi.
- Serwer `redteam/server.py` (tylko 127.0.0.1, log żądań do wykrywania kanarków); testowe mapowanie nazw
  `SANDBOX_TEST_HOSTS`; wyjątki SSRF w testach liczone po IP:port.
- `tests/redteam/test_sanitizer.py` w CI (31/31) + pomiar fałszywych alarmów na stronach łagodnych.
- `redteam/eval_agent.py`: attack success rate, wycieki kanarków, wykonane vs zablokowane wywołania narzędzi,
  poprawność werdyktów; modele mock / gullible / anthropic; workflow `redteam-eval.yml` (workflow_dispatch).
- Pierwsze raporty: `redteam/reports/RAPORT_2026-10-18_{gullible,mock}.md` — 0/31 udanych ataków, 0 wycieków,
  0 wykonanych niedozwolonych narzędzi, 0 fałszywych alarmów, 14/14 poprawnych werdyktów.
- `docs/REDTEAM.md`.

### M7 – Docker + dokumentacja końcowa
- `docker-compose.yml`: db (PostgreSQL 16), mcp-web-sandbox (osobny kontener, streamable HTTP, read-only FS,
  UID 65534, `cap_drop: ALL`, 0,5 CPU / 512 MB, sieci `sandbox`+`egress` bez dostępu do bazy, kontrola nagłówka Host),
  api (API + orkiestrator + newsroom stdio, migracje przy starcie), frontend (nginx, proxy `/api`, SSE), redteam (profil).
- CI: job „Docker compose — build i test dymny” — build stosu, weryfikacja artykułu przez API w kontenerach, testy
  izolacji sandboksa (brak sekretów w env, brak połączenia z bazą, read-only FS).
- Skrypty: `scripts/setup|start|test|redteam.ps1` (ASCII, zgodne z Windows PowerShell 5.1), `scripts/*.sh`, `Makefile`.
- Dokumentacja: README, INSTRUKCJA_URUCHOMIENIA, ARCHITEKTURA (Mermaid), BEZPIECZENSTWO (STRIDE), MCP, METODOLOGIA,
  API, PANEL_REDAKTORA (ze zrzutami ekranu), DECYZJE (D-001…D-017), RAPORT_WYKONANIA.
- Weryfikacja czystego klonu (Windows) i poprawki z niej: `ensure_schema()` (migracje Alembic przy starcie API/seed/
  newsroom zamiast `create_all`, obsługa bazy bez `alembic_version`), skrypty PowerShell bez polskich znaków i z
  kontrolą kodów wyjścia.
