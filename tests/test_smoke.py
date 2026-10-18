"""Test dymny — sprawdza, że pakiety projektu dają się zaimportować."""

import importlib

import pytest


@pytest.mark.parametrize("module", ["backend", "mcp_servers", "orchestrator", "redteam"])
def test_package_imports(module: str) -> None:
    assert importlib.import_module(module) is not None
