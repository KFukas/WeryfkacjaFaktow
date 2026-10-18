"""Wspólne elementy testów red-team: konfiguracja sandboksa dla serwera testowego i indeks wyszukiwania."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from mcp_servers.web_sandbox.settings import SandboxSettings

FAKE_HOSTS = {"gus-dane-oficjalne.test": "127.0.0.1", "rebind.test": "10.255.255.1"}


def sandbox_env(port: int, index_path: Path | str) -> dict[str, str]:
    """Zmienne SANDBOX_* dla procesu sandboksa: wyjątki tylko dla serwera red-team na tym porcie."""
    allow = [f"127.0.0.1:{port}"] + [f"{h}:{port}" for h in FAKE_HOSTS]
    return {
        "SANDBOX_OFFLINE": "1",
        "SANDBOX_TEST_ALLOW": ",".join(allow),
        "SANDBOX_TEST_HOSTS": ",".join(f"{h}={ip}" for h, ip in FAKE_HOSTS.items()),
        "SANDBOX_EXTRA_INDEX": str(index_path),
        "SANDBOX_TIMEOUT_S": "5",
    }


def sandbox_settings(port: int, index_path: Path | str = "") -> SandboxSettings:
    allow = frozenset({("127.0.0.1", port)} | {(h, port) for h in FAKE_HOSTS})
    return replace(SandboxSettings(), offline=True, timeout_s=5.0, test_allow=allow, test_hosts=dict(FAKE_HOSTS),
                   extra_index=str(index_path))


def search_index(cases: list[dict[str, Any]], base_url_for) -> list[dict[str, Any]]:
    out = []
    for c in cases:
        words = re.findall(r"\w{3,}", c["claim"])
        out.append({"provider": "redteam", "title": f"Raport: {c['claim'][:80]}", "url": base_url_for(c),
                    "publisher": "(nieznany wydawca)", "snippet": c["claim"], "keywords": words})
    return out


def write_search_index(cases: list[dict[str, Any]], base_url_for, path: Path) -> Path:
    path.write_text(json.dumps(search_index(cases, base_url_for), ensure_ascii=False, indent=1), encoding="utf-8")
    return path
