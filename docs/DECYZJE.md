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
