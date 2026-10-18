"""Parametry uruchomienia serwerów MCP (bez importów strefy zaufanej — używane też przez launcher)."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULES = {"web-sandbox": "mcp_servers.web_sandbox.server", "newsroom": "mcp_servers.newsroom.server"}

# Jedyne zmienne, które sandbox dostaje z zewnątrz (poza SANDBOX_*). Brak kluczy API, DATABASE_URL, tokenów.
SANDBOX_ENV_ALLOW = {"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
                     "HOME", "USERPROFILE", "LOCALAPPDATA", "LANG", "LC_ALL", "TZ", "PYTHONIOENCODING", "PYTHONUTF8",
                     "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE"}


def sandbox_env(source: Mapping[str, str] | None = None, overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    src = os.environ if source is None else source
    env = {k: v for k, v in src.items() if k.upper() in SANDBOX_ENV_ALLOW or k.upper().startswith("SANDBOX_")}
    env.update({k: v for k, v in (overrides or {}).items() if k.upper().startswith("SANDBOX_")})
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env["PYTHONPATH"] = str(ROOT)
    return env


def venv_python() -> str:
    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable
