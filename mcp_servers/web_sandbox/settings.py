"""Konfiguracja sandboksa — WYŁĄCZNIE ze zmiennych środowiskowych.

Sandbox celowo nie czyta pliku `.env` (tam są sekrety strefy zaufanej) i nie importuje niczego z `backend`
ani `orchestrator`. Launcher (`scripts/run_mcp.py`, docker-compose) przekazuje mu minimalne środowisko.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_RUBRIC = PACKAGE_DIR.parent.parent / "config" / "credibility_rubric.yaml"


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _parse_allow(raw: str) -> frozenset[tuple[str, int]]:
    """`127.0.0.1:8899,redteam:8899` → {(host, port)} — wyjątki od blokady adresów prywatnych (tylko testy)."""
    out: set[tuple[str, int]] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        host, _, port = item.rpartition(":")
        if port.isdigit():
            out.add((host.strip("[]").lower(), int(port)))
    return frozenset(out)


def _parse_hosts(raw: str) -> dict[str, str]:
    """`gus-dane-oficjalne.test=127.0.0.1,rebind.test=10.0.0.1` → {nazwa: ip}."""
    out: dict[str, str] = {}
    for item in raw.split(","):
        name, _, ip = item.strip().partition("=")
        if name and ip:
            out[name.lower()] = ip.strip()
    return out


@dataclass(frozen=True)
class SandboxSettings:
    offline: bool = True
    timeout_s: float = 10.0
    max_bytes: int = 2 * 1024 * 1024
    max_text_chars: int = 20_000
    max_redirects: int = 3
    allowed_ports: frozenset[int] = frozenset({80, 443})
    test_allow: frozenset[tuple[str, int]] = field(default_factory=frozenset)
    # Wyłącznie testy red-team: nazwa → IP (jak /etc/hosts), np. domena-podróbka wskazująca serwer testowy.
    test_hosts: dict[str, str] = field(default_factory=dict)
    rubric_path: Path = DEFAULT_RUBRIC
    extra_index: str = ""  # dodatkowy indeks wyszukiwania offline (np. strony red-team)
    user_agent: str = "KurierFaktowFactCheck/1.0 (https://github.com/KFukas/WeryfkacjaFaktow; projekt edukacyjny) httpx"

    @classmethod
    def from_env(cls) -> SandboxSettings:
        return cls(
            offline=os.environ.get("SANDBOX_OFFLINE", "1") not in ("0", "false", "False", ""),
            timeout_s=float(os.environ.get("SANDBOX_TIMEOUT_S", "10")),
            max_bytes=_int("SANDBOX_MAX_BYTES", 2 * 1024 * 1024),
            max_text_chars=_int("SANDBOX_MAX_TEXT_CHARS", 20_000),
            test_allow=_parse_allow(os.environ.get("SANDBOX_TEST_ALLOW", "")),
            test_hosts=_parse_hosts(os.environ.get("SANDBOX_TEST_HOSTS", "")),
            rubric_path=Path(os.environ.get("SANDBOX_RUBRIC_PATH", str(DEFAULT_RUBRIC))),
            extra_index=os.environ.get("SANDBOX_EXTRA_INDEX", ""),
        )
