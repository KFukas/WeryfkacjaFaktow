# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/), wersjonowanie: [SemVer](https://semver.org/lang/pl/).

## [Unreleased]

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
