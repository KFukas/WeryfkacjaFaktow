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
