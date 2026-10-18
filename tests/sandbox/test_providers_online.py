"""Testy z prawdziwymi publicznymi API (opcjonalne): RUN_NETWORK=1 pytest -m network."""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

from mcp_servers.web_sandbox.settings import SandboxSettings
from mcp_servers.web_sandbox.tools import SandboxTools

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(os.environ.get("RUN_NETWORK") != "1", reason="wymaga RUN_NETWORK=1 i internetu"),
]


@pytest.fixture()
def online() -> SandboxTools:
    return SandboxTools(replace(SandboxSettings.from_env(), offline=False))


def test_wikipedia_search_and_fetch(online):
    res = online.search_public_sources("Rysy szczyt", ["encyclopedia"], limit=3)
    assert res["results"], res
    page = online.fetch_url_sanitized("https://pl.wikipedia.org/wiki/Rysy")
    assert "error" not in page and "2499" in page["text"]
    assert not [f for f in page["injection_flags"] if f["severity"] in ("high", "medium")]  # brak fałszywych alarmów


def test_gus_bdl_unemployment(online):
    out = online.query_dataset("gus_bdl", "60270", {"year": "2023"})
    assert "5.1" in out["text"]


def test_nbp_rate(online):
    out = online.query_dataset("nbp", "exchangerates", {"table": "A", "code": "EUR", "date": "2024-01-02"})
    assert "4.3434" in out["text"]


def test_eurostat_population(online):
    out = online.query_dataset("eurostat", "tps00001", {"geo": "EU27_2020", "time": "2024"})
    assert "449" in out["text"]
