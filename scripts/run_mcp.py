"""Launcher serwerów MCP (używany przez .mcp.json, orkiestrator i skrypty).

  python scripts/run_mcp.py web-sandbox   # strefa NIEUFNA — minimalne środowisko, bez sekretów
  python scripts/run_mcp.py newsroom      # strefa ZAUFANA — pełne środowisko (czyta .env)

Uruchamia serwer interpreterem z `.venv` (Windows: .venv/Scripts/python.exe, Linux/macOS: .venv/bin/python),
jeśli istnieje — dzięki temu `.mcp.json` może używać zwykłego `python` niezależnie od systemu.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVERS = {"web-sandbox": "mcp_servers.web_sandbox.server", "newsroom": "mcp_servers.newsroom.server"}

# Jedyne zmienne, które sandbox dostaje z zewnątrz (poza SANDBOX_*). Brak kluczy API, DATABASE_URL, tokenów.
SANDBOX_ENV_ALLOW = {"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
                     "HOME", "USERPROFILE", "LOCALAPPDATA", "LANG", "LC_ALL", "TZ", "PYTHONIOENCODING", "PYTHONUTF8",
                     "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE"}


def sandbox_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    src = os.environ if source is None else source
    env = {k: v for k, v in src.items() if k.upper() in SANDBOX_ENV_ALLOW or k.upper().startswith("SANDBOX_")}
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env["PYTHONPATH"] = str(ROOT)
    return env


def venv_python() -> str:
    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in SERVERS:
        print(f"użycie: run_mcp.py {{{'|'.join(SERVERS)}}} [argumenty serwera]", file=sys.stderr)
        return 2
    name, extra = sys.argv[1], sys.argv[2:]
    env = sandbox_env() if name == "web-sandbox" else {**os.environ, "PYTHONPATH": str(ROOT)}
    cmd = [venv_python(), "-m", SERVERS[name], *extra]
    # stdio dziedziczone — serwer MCP rozmawia bezpośrednio z klientem przez stdin/stdout.
    return subprocess.call(cmd, cwd=str(ROOT), env=env)  # noqa: S603


if __name__ == "__main__":
    sys.exit(main())
