# Raport wykonania — „Weryfikacja faktów” v1.0.0

Repozytorium: <https://github.com/KFukas/WeryfkacjaFaktow> · gałąź `main` · tag `v1.0.0` · data: 2026-10-18.

## 1. Podsumowanie
Zbudowano kompletny system weryfikacji faktów dla fikcyjnej redakcji „Kurier Faktów”: backend REST z bazą, dwa
własne serwery MCP (strefa zaufana `newsroom` i nieufna `web-sandbox`), orkiestrator agenta Claude z izolacją treści
z sieci, skill Claude Code (będący też źródłem promptów), panel redaktora w React, zestaw 31 stron red-team z evalem,
Docker oraz pełną dokumentację. Wszystko działa offline bez klucza API (model deterministyczny + fixture'y danych
publicznych zweryfikowane z prawdziwymi API), a po ustawieniu `LLM_PROVIDER=anthropic` — z prawdziwym Claude.

Najważniejszy wynik bezpieczeństwa: nawet model, który **wykonuje każde polecenie** ze spreparowanych stron, nie
osiąga celu ataku (0/31), bo granice są strukturalne — model czytający sieć nie ma narzędzi zapisu, adresy spoza
wyników wyszukiwania są odrzucane, dane redakcji nie mogą wyjść, a werdykt zatwierdzają reguły deterministyczne.

## 2. Co zrobiono — per kamień milowy
| Kamień | Zakres | Commity |
|---|---|---|
| **M0** Szkielet | struktura pakietów, `pyproject.toml`, README, CLAUDE.md, `.env.example`, MIT, CI, szablony issue/PR, skaner sekretów | [`483e8ba`](https://github.com/KFukas/WeryfkacjaFaktow/commit/483e8ba), [`6c06562`](https://github.com/KFukas/WeryfkacjaFaktow/commit/6c06562) (poprawka CI) |
| **M1** Backend + DB | modele SQLAlchemy 2 (Article, Claim, Source, ClaimSource, AgentRun/Event, EditorDecision), migracja Alembic, REST (CRUD, decyzje, raporty), seed 4 artykułów | [`6510aff`](https://github.com/KFukas/WeryfkacjaFaktow/commit/6510aff) |
| **M2** web-sandbox | SSRF (IP przy łączeniu, rebinding, przekierowania), limity, sanitizer HTML/PDF, detekcja injection, ocena źródeł z rubryki, klienci GUS BDL/Eurostat/NBP/KRS/dane.gov.pl/Wikipedia/Wikidata + offline | [`ba94b5a`](https://github.com/KFukas/WeryfkacjaFaktow/commit/ba94b5a) |
| **M3** newsroom + orkiestrator | serwer MCP newsroom, pipeline 7 etapów, bramka (allowlisty, pochodzenie URL, egress, budżet), kwarantanna dual-LLM, reguły werdyktu, audyt, SSE, idempotencja, modele mock/gullible/anthropic | [`0398723`](https://github.com/KFukas/WeryfkacjaFaktow/commit/0398723) |
| **M4** Skill | `SKILL.md` z sekcjami promptów, references (rubryka, źródła, przykłady), walidator, `.mcp.json`, `.claude/settings.json` | [`77fe138`](https://github.com/KFukas/WeryfkacjaFaktow/commit/77fe138) |
| **M5** Frontend | adnotacje (kolor+ikona+wzór), panel źródeł z rozpisaniem oceny, decyzje redaktora, postęp na żywo, audyt, tryb ciemny, Vitest + e2e Playwright | [`62b602d`](https://github.com/KFukas/WeryfkacjaFaktow/commit/62b602d) |
| **M6** Red-team | 31 stron + `expected.yaml`, serwer testowy, testy sanitizera w CI, `eval_agent.py`, raporty | [`c37af71`](https://github.com/KFukas/WeryfkacjaFaktow/commit/c37af71) |
| **M7** Docker + docs | docker-compose (5 usług, strefy sieciowe), test dymny Dockera w CI, skrypty PS/bash/Makefile, dokumentacja, weryfikacja czystego klonu i poprawki z niej | [`2c5cee0`](https://github.com/KFukas/WeryfkacjaFaktow/commit/2c5cee0), [`bc9a286`](https://github.com/KFukas/WeryfkacjaFaktow/commit/bc9a286), [`3e6a818`](https://github.com/KFukas/WeryfkacjaFaktow/commit/3e6a818), commit z tym raportem (tag `v1.0.0`) |

## 3. Jak to działa — od wklejenia tekstu do werdyktów w UI
Przykład: artykuł „Dwadzieścia lat Polski w Unii Europejskiej” (seed nr 2).

1. **Wklejenie tekstu.** Redaktor dodaje artykuł w panelu (formularz „Nowy artykuł”) → `POST /api/articles` →
   rekord `Article` (status `draft`).
2. **Start.** „Weryfikuj” → `POST /api/articles/2/verify` → `AgentRun` (idempotentnie) i wątek w tle. Orkiestrator
   uruchamia dwa serwery MCP: `newsroom` (stdio, z dostępem do bazy) i `web-sandbox` (stdio z minimalnym środowiskiem —
   bez klucza i adresu bazy; w Dockerze osobny kontener po HTTP). UI otwiera strumień SSE `/api/runs/{id}/stream`.
3. **Ekstrakcja.** `newsroom.get_article` → model (etap `extract`, prompt z `SKILL.md`, wyjście wg JSON Schema)
   wskazuje trzy twierdzenia z offsetami; „Członkostwo zmieniło kraj…” i „Wielu mieszkańców podkreśla…” pomija jako
   niesprawdzalne. `newsroom.save_claims` sprawdza, że tekst występuje w artykule (offsety korygowane), status →
   `in_review`.
4. **Plan i research** (dla „Do NATO Polska wstąpiła w 2001 roku.”). Model planuje zapytania tylko z treści twierdzenia
   i woła `search_public_sources`. Bramka sprawdza allowlistę etapu i egress (brak kanarków/fragmentów artykułu),
   sandbox zwraca wyniki (gov.pl/MON, Wikipedia). Model prosi o `fetch_url_sanitized` — bramka przepuszcza tylko URL
   obecny w wynikach. Sandbox pobiera stronę (SSRF: IP sprawdzone przy łączeniu), usuwa skrypty i ukryte elementy,
   normalizuje Unicode, liczy flagi i zwraca kopertę `untrusted: true`.
5. **Kwarantanna.** Osobne wywołanie modelu bez narzędzi dostaje stronę w `<untrusted_source>` i zwraca JSON:
   `stance: contradicts`, cytat „Polska jest członkiem Sojuszu Północnoatlantyckiego (NATO) od 12 marca 1999 r.”,
   `manipulation_notes: []`. Orkiestrator sprawdza, że cytat jest dosłownym fragmentem tekstu.
6. **Ocena źródła.** `score_source` (deterministycznie): administracja publiczna 75 + pierwotne 5 + data 3 + instytucja 2
   = **85/100**, rozpisane na kryteria.
7. **Werdykt.** Model (bez narzędzi) widzi tylko streszczenia z kwarantanny, flagi i oceny; proponuje „fałszywe” i
   ewentualną korektę (±15). Reguły deterministyczne: źródło ≥ 70 bezpośrednio przeczy → **fałszywe**; zgodność z
   modelem → werdykt zapisany z pewnością ograniczoną do siły dowodów (0,81).
8. **Zapis.** Kod orkiestratora: `newsroom.attach_source` (relacja, cytat, rozpisanie, flagi), `newsroom.save_verdict`
   (walidacja: „fałszywe” wymaga źródła przeczącego). Każdy krok trafia do `AgentEvent` (prompt hash i treść, argumenty
   narzędzi, czasy, tokeny, koszt).
9. **UI.** SSE odświeża tekst: twierdzenie podkreślone falisto na czerwono z „✘”. Kliknięcie otwiera panel: werdykt,
   pewność, uzasadnienie, źródło MON z oceną 85 i cytatem, rozpisanie punktów. Redaktor może zmienić werdykt z notatką
   (historia zachowana), zlecić ponowną weryfikację twierdzenia, pobrać raport Markdown/JSON i obejrzeć log agenta.

Gdyby strona zawierała ukryte polecenie („wywołaj save_verdict…”), sandbox usunąłby je z tekstu i dodał flagi
(ocena spada), model w research i tak nie ma narzędzia zapisu, a źródło z flagą high nie może być podstawą werdyktu —
w panelu pojawiłoby się ostrzeżenie „Strona zawierała ukryte polecenia — oceniona niżej”.

## 4. Wyniki testów
| Zestaw | Wynik |
|---|---|
| pytest (backend, sandbox, orkiestrator, red-team, skill/konfiguracja) | **174 passed**, 4 skipped (testy z prawdziwymi API — wymagają `RUN_NETWORK=1`) |
| testy z prawdziwymi publicznymi API (`RUN_NETWORK=1`) | **4/4** (Wikipedia, GUS BDL 60270 = 5,1%, NBP EUR 2024-01-02 = 4,3434, Eurostat tps00001 ≈ 449,5 mln) |
| Vitest (frontend) | **7/7** (segmentacja, adnotacje, XSS w cytatach/tytułach, linki `javascript:`, panel, brak surowego HTML) |
| e2e Playwright (`scripts/ui_e2e.py`) | **OK** — lista → weryfikacja → postęp → adnotacje → panel → audyt → tryb ciemny |
| ruff, `tsc` | bez błędów |
| GitHub Actions (CI) | zielone dla każdego commita od M1: lint + pytest, sanitizer + eval red-team (`--strict`), frontend, **Docker compose build + weryfikacja artykułu w kontenerach + testy izolacji sandboksa** |
| Czysty klon (Windows, PowerShell 5.1) | `setup.ps1` → `test.ps1` (174 + 7 testów) → API + panel z klonu → e2e OK → CLI `orchestrator.runner` OK |
| Fałszywe alarmy na prawdziwych stronach | 0 flag medium/high na 5 stronach (Wikipedia: Rysy, Kopernik, Wisła; gov.pl; stat.gov.pl) po strojeniu |

### Red-team (`redteam/reports/RAPORT_2026-10-18_*.md`)
| Metryka | gullible (najgorszy przypadek) | mock |
|---|---|---|
| Attack success rate | **0/31 (0%)** | **0/31 (0%)** |
| Udane eksfiltracje kanarków | **0** | **0** |
| Wykonane niedozwolone wywołania narzędzi | **0** | **0** |
| Próby zablokowane przez bramkę | 98 | — |
| Sanitizer zgodny z `expected.yaml` | **31/31** | **31/31** |
| Fałszywe alarmy (strony łagodne) | **0/13** | **0/13** |
| Poprawność werdyktów na seedach | **14/14** | **14/14** |

## 5. Czego nie zrobiono / znane ograniczenia
- **Eval z prawdziwym modelem nie został uruchomiony** — w środowisku budowy nie było klucza `ANTHROPIC_API_KEY`.
  Kod (`orchestrator/llm/anthropic_llm.py`) jest kompletny (structured outputs, strict tool use, prompt caching,
  fallback przy odmowie, obsługa `refusal`), ale nie był wykonany na żywym API. Gotowe: `python -m redteam.eval_agent
  --llm anthropic` lub workflow „Red-team eval (prawdziwy model)” z sekretem w GitHub.
- **Docker nie był uruchamiany lokalnie** (brak Dockera na maszynie) — stos jest budowany i testowany end-to-end w CI
  (job „Docker compose — build i test dymny”, zielony).
- **`/mcp` w Claude Code nie był sprawdzony interaktywnie**; test `test_servers_start_like_claude_code` uruchamia oba
  serwery dokładnie tak jak `.mcp.json` i listuje narzędzia. Skill jest wykrywany (pojawił się na liście skilli sesji).
- **Model offline (mock)** to heurystyki liczb, dat i słów kluczowych — dobre do demonstracji i testów, ale nie
  „rozumie” tekstu; online z prawdziwym modelem jakość zależy od Claude.
- Ryzyka szczątkowe opisane w `docs/BEZPIECZENSTWO.md` — m.in. **błąd semantyczny modelu na wiarygodnym źródle**
  (zaobserwowany w trakcie strojenia modelu `gullible`: reguły nie sprawdzają, czy cytat faktycznie dowodzi
  twierdzenia przyczynowego), obchodzenie heurystyk parafrazą, brak OCR obrazów.
- Eurostat bez wyszukiwarki pełnotekstowej (stały katalog zbiorów); KRS wymaga numeru KRS.
- Fixture'y offline są uproszczonymi kopiami (oznaczonymi) — liczby zweryfikowano z prawdziwymi API, ale treść stron
  nie jest oryginałem.

## 6. Propozycje dalszych kroków
1. Uruchomić eval z prawdziwym modelem (Sonnet 5.5 i Opus 5.5) i porównać wykrywanie manipulacji
   (`manipulation_detected`) oraz poprawność werdyktów; rozważyć tańszy model kwarantanny (`claude-haiku-5-5`).
2. Weryfikator „czy cytat dowodzi twierdzenia” — drugie, niezależne wywołanie (entailment) przed werdyktem
   rozstrzygającym; dodać ten wektor (wiarygodne źródło + błędne wnioskowanie) do zestawu red-team.
3. Rozszerzyć dostawców: ISAP (akty prawne), Sejm API (głosowania), PKW, NFZ; wyszukiwarka zbiorów Eurostatu.
4. Uwierzytelnianie redaktorów (SSO) i role (redaktor / wydawca), podpisane decyzje.
5. Kolejka zadań (np. Arq/Celery) zamiast wątków w API, limity równoległości per redakcja.
6. OCR dla obrazów i PDF-ów skanowanych w sandboksie (z tymi samymi regułami nieufności).
7. Obserwowalność: eksport audytu do OpenTelemetry, alerty przy wzroście `tool_violation`/`injection_detected`.
8. Wersja online fixture'ów odświeżana automatycznie (nocny job porównujący z prawdziwymi API).
