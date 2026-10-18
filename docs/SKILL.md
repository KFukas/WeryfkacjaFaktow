# Skill „weryfikacja-faktow”

Skill Claude Code w `.claude/skills/weryfikacja-faktow/` opisuje, jak weryfikować artykuły redakcji. Pełni dwie role:

1. **Instrukcja dla Claude Code** — przy pracy interaktywnej („zweryfikuj artykuł 3”) Claude wczytuje skill i
   wykonuje procedurę narzędziami serwerów MCP `newsroom` i `web-sandbox`.
2. **Źródło promptów orkiestratora** — `orchestrator/prompts.py` wycina z `SKILL.md` sekcje
   `<!-- prompt:NAZWA --> … <!-- /prompt -->` i używa ich jako promptów systemowych etapów. Zmiana instrukcji w skillu
   zmienia zachowanie agenta w API — bez duplikowania tekstów w kodzie.

## Struktura
```
.claude/skills/weryfikacja-faktow/
├── SKILL.md                     # frontmatter (name, description) + procedura + sekcje promptów
├── references/
│   ├── rubryka.md               # skrót rubryki wiarygodności (dołączany do promptu etapu werdyktu)
│   ├── zrodla-publiczne.md      # katalog API i rejestrów (GUS BDL, Eurostat, NBP, KRS, dane.gov.pl, Wikimedia)
│   └── przyklady.md             # przykłady werdyktów, w tym próba prompt injection i poprawna reakcja
└── scripts/
    └── validate_verdicts.py     # walidacja JSON werdyktów (schemat + zgodność z regułami)
```

## Kiedy się włącza
Pole `description` we frontmatterze decyduje o automatycznym wyborze skilla. Włącza się przy prośbach o sprawdzenie
artykułu, twierdzenia, liczby lub cytatu („zweryfikuj artykuł 3”, „sprawdź, czy to prawda”, „fact-check”) oraz o ocenę
wiarygodności źródła. Nie włącza się przy pisaniu tekstów ani zwykłym wyszukiwaniu. Ręcznie: `/weryfikacja-faktow`.

## Sekcje promptów
| Sekcja | Etap orkiestratora | Narzędzia modelu |
|---|---|---|
| `system` | wspólne zasady bezpieczeństwa (dołączane do każdego etapu) | — |
| `extract` | ekstrakcja twierdzeń z offsetami | brak (structured output) |
| `plan` | planowanie zapytań | brak |
| `research` | wyszukiwanie źródeł | `search_public_sources`, `query_dataset`, `fetch_url_sanitized` |
| `quarantine` | ekstrakcja z nieufnego źródła (dual-LLM) | brak |
| `verdict` | ocena relacji, korekta ±15, propozycja werdyktu (+ `references/rubryka.md`) | brak |

## Uprawnienia w Claude Code
`.claude/settings.json`: narzędzia odczytu (`web-sandbox.*`, `newsroom.get_article`, `list_pending_articles`) są
dozwolone bez pytania, zapis (`save_claims`, `attach_source`, `save_verdict`) wymaga potwierdzenia, `.env` i
wbudowany `WebFetch` są zablokowane — strony pobieramy wyłącznie przez sandbox.

## Jak rozszerzać
- **Zmiana instrukcji etapu:** edytuj treść między znacznikami `<!-- prompt:… -->`. Nie usuwaj znaczników — test
  `tests/orchestrator/test_rules_egress_prompts.py::test_skill_sections_are_prompt_source` sprawdza ich obecność.
- **Nowy etap:** dodaj sekcję `<!-- prompt:nowy -->`, dopisz nazwę do `orchestrator/prompts.STAGES` i użyj
  `prompts.system_prompt("nowy")` w pipeline. Jeśli etap ma dostać narzędzia, dopisz je do `LLM_ALLOWLIST`
  w `orchestrator/gateway.py` (tylko narzędzia odczytu strefy nieufnej!).
- **Nowe źródło danych:** dostawca w `mcp_servers/web_sandbox/providers.py` + domena w
  `config/credibility_rubric.yaml` + wiersz w `references/zrodla-publiczne.md`.
- **Nowy przykład:** dopisz do `references/przyklady.md` (służy ludziom i modelowi w trybie interaktywnym).
- Po zmianach: `pytest tests/test_skill_config.py tests/orchestrator`.
