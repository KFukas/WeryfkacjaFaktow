# Instrukcja uruchomienia

## Wymagania
| Składnik | Wersja | Uwagi |
|---|---|---|
| Python | **3.12** | Windows: launcher `py -3.12`; Linux/macOS: `python3.12` |
| Node.js | 20+ (testowane 22/24) | npm 10+ |
| Git | dowolny aktualny | |
| Docker + Compose v2.24+ | opcjonalnie | do uruchomienia całego stosu w kontenerach |
| Klucz Anthropic API | opcjonalnie | bez klucza działa model offline (`LLM_PROVIDER=mock`) |

## Konfiguracja `.env`
Skrypty instalacyjne kopiują `.env.example` → `.env`. Najważniejsze zmienne:

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` (offline, bez kosztów) albo `anthropic` (prawdziwy Claude) |
| `ANTHROPIC_API_KEY` | — | wymagany dla `anthropic`; **nigdy nie commituj** (plik `.env` jest w `.gitignore`) |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | albo `claude-opus-5-5` dla trudniejszych artykułów |
| `ANTHROPIC_QUARANTINE_MODEL` | (pusty = jak główny) | model kwarantanny źródeł, np. tańszy `claude-haiku-5-5` |
| `ANTHROPIC_EFFORT` | `medium` | `low` … `max` |
| `ANTHROPIC_FALLBACKS` | `default` | serwerowy fallback przy odmowie modelu; `off` wyłącza |
| `DATABASE_URL` | `sqlite:///./data/kurier.db` | Docker: PostgreSQL |
| `AGENT_MAX_CLAIMS` / `AGENT_MAX_TOOL_CALLS` / `AGENT_MAX_COST_USD` | 12 / 60 / 1.50 | limity na artykuł |
| `SANDBOX_OFFLINE` | `1` | `1` = publiczne API i strony z fixture'ów (deterministycznie); `0` = prawdziwy internet |

## Uruchomienie lokalne — Windows (PowerShell)
```powershell
git clone https://github.com/KFukas/WeryfkacjaFaktow.git
cd WeryfkacjaFaktow
.\scripts\setup.ps1      # venv 3.12, zależności, .env, migracje, dane przykładowe, npm install
.\scripts\start.ps1      # API :8000 i panel :5173 w osobnych oknach
```
Panel: <http://127.0.0.1:5173> · API/OpenAPI: <http://127.0.0.1:8000/docs>.
Testy: `.\scripts\test.ps1` · eval red-team: `.\scripts\redteam.ps1` (opcjonalnie `-Llm mock|anthropic`).

Jeśli PowerShell blokuje skrypty: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## Uruchomienie lokalne — Linux / macOS / Git Bash
```bash
git clone https://github.com/KFukas/WeryfkacjaFaktow.git && cd WeryfkacjaFaktow
scripts/setup.sh         # albo: make setup
scripts/start.sh         # albo: make start  (Ctrl+C zatrzymuje)
```
Testy: `scripts/test.sh` (`make test`) · red-team: `make redteam`.

### Ręcznie (krok po kroku)
```bash
python3.12 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head && python -m backend.seed
uvicorn backend.main:app --port 8000                       # terminal 1
cd frontend && npm install && npm run dev                   # terminal 2
python -m orchestrator.runner --article 2                   # weryfikacja z linii poleceń (opcjonalnie)
```

## Uruchomienie w Dockerze
```bash
cp .env.example .env          # opcjonalnie: klucz API, LLM_PROVIDER=anthropic
docker compose up --build     # UI: http://localhost:8080  API: http://localhost:8000/docs
docker compose --profile redteam up --build   # + serwer stron red-team w sieci sandboksa
docker compose down -v        # zatrzymanie i usunięcie danych
```
Kontenery: `db` (PostgreSQL 16), `mcp-web-sandbox` (sandbox po HTTP: read-only FS, użytkownik bez uprawnień,
0,5 CPU / 512 MB, sieci `sandbox` + `egress` — bez dostępu do bazy), `api` (API + orkiestrator + newsroom MCP),
`frontend` (nginx z buildem React, proxy `/api`), `redteam` (profil `redteam`, IP 172.28.5.99 w sieci sandboksa).
Aby sandbox w Dockerze mógł pobierać strony red-team, ustaw w `.env`:
`SANDBOX_TEST_ALLOW=172.28.5.99:8899,redteam:8899` (wyłącznie do testów!).

CI na GitHubie buduje cały stos, uruchamia weryfikację artykułu przez API w kontenerach i sprawdza izolację sandboksa
(job „Docker compose — build i test dymny”).

## Podłączenie MCP do Claude Code
1. Wykonaj instalację lokalną (potrzebny `.venv`).
2. Otwórz Claude Code w katalogu repozytorium — `.mcp.json` rejestruje serwery `web-sandbox` i `newsroom`,
   `.claude/settings.json` je włącza (przy pierwszym uruchomieniu Claude Code może poprosić o zatwierdzenie).
3. Sprawdź: `/mcp` → oba serwery „connected”. Skill `weryfikacja-faktow` jest wykrywany automatycznie
   (lista skilli / `/weryfikacja-faktow`).
4. Przykład: „zweryfikuj artykuł 2”. Zapis werdyktów (`save_verdict` itd.) wymaga potwierdzenia.

`.mcp.json` używa polecenia `python` — musi być w `PATH` (dowolny Python ≥ 3.10; launcher sam przełącza się na
interpreter z `.venv`).

## Podłączenie do Claude Desktop
Dodaj do `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\`, macOS: `~/Library/Application Support/Claude/`):
```json
{"mcpServers": {
  "web-sandbox": {"command": "python", "args": ["C:/sciezka/WeryfkacjaFaktow/scripts/run_mcp.py", "web-sandbox"],
                  "env": {"SANDBOX_OFFLINE": "1"}},
  "newsroom":    {"command": "python", "args": ["C:/sciezka/WeryfkacjaFaktow/scripts/run_mcp.py", "newsroom"]}
}}
```

## Test e2e w przeglądarce (opcjonalnie)
```bash
pip install -e ".[e2e]" && playwright install chromium
python scripts/ui_e2e.py --screenshots docs/img     # przy uruchomionym API i panelu
```

## Rozwiązywanie problemów
| Objaw | Przyczyna / rozwiązanie |
|---|---|
| `py -3.12` nie działa | zainstaluj Python 3.12 (python.org) albo ustaw `PYTHON=python3.12` dla `setup.sh` |
| Panel: „Nie można połączyć się z API” | API nie działa na :8000; uruchom `uvicorn backend.main:app --port 8000`; w dev Vite przekazuje `/api` na 127.0.0.1:8000 (`VITE_API_PROXY`) |
| Przebieg kończy się `failed: LLM_PROVIDER=anthropic wymaga ANTHROPIC_API_KEY` | uzupełnij klucz w `.env` albo ustaw `LLM_PROVIDER=mock` |
| Przebieg `budget_exceeded` | zwiększ `AGENT_MAX_TOOL_CALLS` / `AGENT_MAX_COST_USD` |
| Same werdykty „wątpliwe” w trybie online | publiczne API mogą nie zwracać danych dla zapytania; sprawdź log agenta (zakładka „Log agenta”) — `errors` w wynikach wyszukiwania |
| Wikipedia zwraca 403 | Wikimedia wymaga identyfikującego User-Agenta — ustawiony w `SandboxSettings.user_agent` |
| `/mcp` w Claude Code: serwer „failed” | brak `.venv` (uruchom setup) albo `python` spoza `PATH`; test: `python scripts/run_mcp.py web-sandbox` (powinien czekać na stdin) |
| Znaki `�` w konsoli Windows | `set PYTHONIOENCODING=utf-8` (skrypty projektu ustawiają UTF-8 same) |
| Docker: `env_file` z `required: false` nie działa | zaktualizuj Docker Compose do v2.24+ albo utwórz pusty `.env` |
| `pip install` na Windows: `OSError: [Errno 2] No such file or directory: …\anthropic\types\beta\…` | limit 260 znaków ścieżki — sklonuj repozytorium do krótkiej ścieżki (np. `C:\Projekty\WeryfkacjaFaktow`) albo włącz długie ścieżki (`LongPathsEnabled` w rejestrze / zasadach grupy) |
| `setup.ps1`: błędy parsera z „krzaczkami” | używasz zmodyfikowanego skryptu z polskimi znakami bez BOM — skrypty `.ps1` w repo są celowo w ASCII (Windows PowerShell 5.1 czyta je jako ANSI) |
| SQLite „database is locked” | zatrzymaj inne procesy używające `data/kurier.db`; WAL jest włączony, timeout 30 s |
