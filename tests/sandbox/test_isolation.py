"""Izolacja strefy nieufnej: brak importów strefy zaufanej, brak sekretów, działający serwer MCP (stdio)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_sandbox_does_not_import_trusted_zone():
    code = ("import sys, mcp_servers.web_sandbox.server as s; s.tools();"
            "print([m for m in sys.modules if m.split('.')[0] in ('backend','orchestrator','sqlalchemy','anthropic')])")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, check=True)
    assert out.stdout.strip() == "[]", out.stdout


def test_sandbox_source_has_no_trusted_imports():
    for py in (ROOT / "mcp_servers" / "web_sandbox").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for bad in ("from backend", "import backend", "from orchestrator", "import orchestrator", "dotenv",
                    "ANTHROPIC_API_KEY", "DATABASE_URL"):
            assert bad not in text, f"{py.name}: {bad}"


def test_sandbox_settings_ignore_dotenv(tmp_path, monkeypatch):
    from mcp_servers.web_sandbox.settings import SandboxSettings

    monkeypatch.delenv("SANDBOX_TEST_ALLOW", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("SANDBOX_TEST_ALLOW=127.0.0.1:22\n")
    assert SandboxSettings.from_env().test_allow == frozenset()


def test_launcher_strips_secrets():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import run_mcp
    finally:
        sys.path.pop(0)
    env = run_mcp.sandbox_env({"ANTHROPIC_API_KEY": "sk-ant-xxx", "DATABASE_URL": "sqlite:///x", "PATH": "/bin",
                               "SANDBOX_OFFLINE": "1", "GITHUB_TOKEN": "ghp_x", "AWS_SECRET_ACCESS_KEY": "y"})
    assert "ANTHROPIC_API_KEY" not in env and "DATABASE_URL" not in env and "GITHUB_TOKEN" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert env["SANDBOX_OFFLINE"] == "1" and env["PATH"] == "/bin"


async def test_mcp_stdio_server_tools():
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_servers.web_sandbox.server"],
                                   env={"SANDBOX_OFFLINE": "1"}, cwd=str(ROOT))
    async with Client(params) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert names == {"search_public_sources", "query_dataset", "fetch_url_sanitized", "score_source"}
        res = await client.call_tool("search_public_sources", {"query": "NATO Polska wstąpiła"})
        data = res.structured_content
        if data is None:
            data = json.loads(res.content[0].text)
        assert any("nato" in r["url"] for r in data["results"])
        res = await client.call_tool("fetch_url_sanitized", {"url": "http://169.254.169.254/latest/"})
        data = res.structured_content or json.loads(res.content[0].text)
        assert data["error"] == "ssrf_blocked"
