# Katalog publicznych źródeł danych

Wszystkie źródła są odpytywane **wyłącznie** przez serwer MCP `web-sandbox` (hosty API są stałe w kodzie, ruch przechodzi
przez ochronę SSRF). W trybie offline (`SANDBOX_OFFLINE=1`) odpowiedzi pochodzą z fixture'ów
`mcp_servers/web_sandbox/fixtures/` — liczby zweryfikowane z prawdziwymi API w październiku 2026.

| Dostawca (`provider`) | Co zawiera | Narzędzie | Endpoint (online) | Typ w rubryce |
|---|---|---|---|---|
| `gus_bdl` | Bank Danych Lokalnych GUS — tysiące zmiennych (rynek pracy, ludność, ceny…) | `search_public_sources` (wyszukiwanie zmiennych), `query_dataset(dataset_id=<id zmiennej>, params={year, unit-level})` | `https://bdl.stat.gov.pl/api/v1/variables/search`, `/data/by-variable/{id}` | urząd statystyczny |
| `gus` | Publikacje i komunikaty stat.gov.pl (w trybie offline — archiwum stron) | `search_public_sources`, `fetch_url_sanitized` | `https://stat.gov.pl/…` | urząd statystyczny |
| `eurostat` | Statystyki UE (JSON-stat) — np. `tps00001` ludność, `prc_hicp_aind` HICP, `une_rt_a` bezrobocie, `nama_10_gdp` PKB | `query_dataset(dataset_id=<kod>, params={geo, time, …})` | `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{kod}` | urząd statystyczny |
| `nbp` | Kursy walut (tabele A/B/C) i ceny złota | `query_dataset("nbp", "exchangerates", {table, code, date})`, `query_dataset("nbp", "cenyzlota", {date})` | `https://api.nbp.pl/api/exchangerates/rates/{t}/{kod}/{data}/` | bank centralny |
| `krs` | Krajowy Rejestr Sądowy — odpis aktualny podmiotu | `query_dataset("krs", "<10 cyfr KRS>", {rejestr: P\|S})` | `https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/{krs}` | rejestr publiczny |
| `dane_gov` | Portal dane.gov.pl — zbiory danych instytucji publicznych | `search_public_sources`, `query_dataset("dane_gov", "<id>")` | `https://api.dane.gov.pl/1.4/search`, `/datasets/{id}` | dane pierwotne |
| `wikipedia` | Encyklopedia (PL/EN) — źródło **wtórne**, dobre do kontekstu i znalezienia źródeł pierwotnych | `search_public_sources`, `fetch_url_sanitized` | `https://{pl,en}.wikipedia.org/w/api.php` | encyklopedia |
| `wikidata` | Dane strukturalne o encjach (Q-id, właściwości P…) | `query_dataset("wikidata", "Q36", {properties: "P1082"})` | `https://www.wikidata.org/wiki/Special:EntityData/{Q}.json` | encyklopedia |
| `gov_pl`, `nobelprize` | Strony instytucji (offline — archiwum; online — tylko z wyników wyszukiwania) | `fetch_url_sanitized` | `https://www.gov.pl/…`, `https://www.nobelprize.org/…` | administracja / naukowe |

## Wskazówki
- **Liczby i statystyki** → najpierw `gus_bdl`/`eurostat`/`nbp` (dane z API dostają +5 w rubryce), potem strona
  publikacji, na końcu encyklopedia.
- **Daty historyczne** → gov.pl / organizacje międzynarodowe; Wikipedia tylko jako kontekst.
- **Podmioty gospodarcze** → `krs` (numer KRS musi pochodzić z twierdzenia albo z wiarygodnego źródła, nie z dowolnej strony).
- **Kursy walut** → `nbp` z dokładną datą; kurs z innej daty to inny fakt.
- Wikipedia i Wikidata to jedna grupa niezależności (`wikimedia`).

## Ograniczenia
- Eurostat nie ma wyszukiwarki pełnotekstowej w API — korzystamy ze stałego katalogu zbiorów
  (`fixtures/eurostat_catalog.json`).
- Wikimedia wymaga identyfikującego User-Agenta (ustawiony w `SandboxSettings.user_agent`).
- Limity zapytań publicznych API — przy błędach `http_error` nie ponawiaj w pętli.
