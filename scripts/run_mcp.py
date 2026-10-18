"""Launcher serwerów MCP (używany przez .mcp.json i skrypty).

  python scripts/run_mcp.py web-sandbox   # strefa NIEUFNA — minimalne środowisko, bez sekretów
  python scripts/run_mcp.py newsroom      # strefa ZAUFANA — pełne środowisko (czyta .env)

Uruchamia serwer interpreterem z `.venv` (Windows: .venv/Scripts/python.exe, Linux/macOS: .venv/bin/python),
jeśli istnieje — dzięki temu `.mcp.json` może używać zwykłego `python` niezależnie od systemu.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_servers.launch import MODULES, ROOT, sandbox_env, venv_python  # noqa: E402

__all__ = ["sandbox_env", "main"]


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in MODULES:
        print(f"użycie: run_mcp.py {{{'|'.join(MODULES)}}} [argumenty serwera]", file=sys.stderr)
        return 2
    name, extra = sys.argv[1], sys.argv[2:]
    env = sandbox_env() if name == "web-sandbox" else {**os.environ, "PYTHONPATH": str(ROOT)}
    cmd = [venv_python(), "-m", MODULES[name], *extra]
    # stdio dziedziczone — serwer MCP rozmawia bezpośrednio z klientem przez stdin/stdout.
    return subprocess.call(cmd, cwd=str(ROOT), env=env)  # noqa: S603


if __name__ == "__main__":
    sys.exit(main())
