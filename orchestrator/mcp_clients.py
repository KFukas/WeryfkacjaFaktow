"""Połączenia orkiestratora z serwerami MCP (stdio / streamable HTTP / w procesie — tylko testy)."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from mcp_servers.launch import MODULES, ROOT, sandbox_env, venv_python


@dataclass
class McpTools:
    name: str
    client: Client

    async def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.call_tool(tool, args)
        data = res.structured_content
        if data is None:
            text = "".join(getattr(c, "text", "") for c in res.content)
            try:
                data = json.loads(text) if text else {}
            except ValueError:
                data = {"error": "invalid_response", "message": text[:500]}
        if res.is_error and isinstance(data, dict):
            data.setdefault("error", "tool_error")
        return data if isinstance(data, dict) else {"result": data}

    async def list_tool_names(self) -> set[str]:
        return {t.name for t in (await self.client.list_tools()).tools}


def _sandbox_target(transport: str, url: str, overrides: Mapping[str, str] | None):
    if transport == "http":
        return url
    if transport == "inproc":
        from mcp_servers.web_sandbox import server as sandbox_server

        return sandbox_server.server
    return StdioServerParameters(command=venv_python(), args=["-m", MODULES["web-sandbox"]],
                                 env=sandbox_env(overrides=overrides), cwd=str(ROOT))


def _newsroom_target(transport: str, database_url: str):
    if transport == "inproc":
        from mcp_servers.newsroom import server as newsroom_server

        return newsroom_server.server
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("SANDBOX_TEST_ALLOW",)}
    env.update({"DATABASE_URL": database_url, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"})
    return StdioServerParameters(command=venv_python(), args=["-m", MODULES["newsroom"]], env=env, cwd=str(ROOT))


@asynccontextmanager
async def connect(sandbox_transport: str, sandbox_url: str, newsroom_transport: str, database_url: str,
                  sandbox_overrides: Mapping[str, str] | None = None) -> AsyncIterator[tuple[McpTools, McpTools]]:
    async with AsyncExitStack() as stack:
        sandbox = await stack.enter_async_context(
            Client(_sandbox_target(sandbox_transport, sandbox_url, sandbox_overrides), read_timeout_seconds=60))
        newsroom = await stack.enter_async_context(
            Client(_newsroom_target(newsroom_transport, database_url), read_timeout_seconds=60))
        yield McpTools("web-sandbox", sandbox), McpTools("newsroom", newsroom)
