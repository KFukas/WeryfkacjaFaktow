# Strefa ZAUFANA: REST API + orkiestrator + serwer MCP newsroom (stdio, proces potomny).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONIOENCODING=utf-8
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY orchestrator ./orchestrator
COPY mcp_servers ./mcp_servers
COPY redteam/__init__.py ./redteam/__init__.py
RUN pip install ".[postgres]"
COPY alembic.ini ./
COPY alembic ./alembic
COPY config ./config
COPY .claude/skills ./.claude/skills
COPY docker/api-entrypoint.sh /usr/local/bin/api-entrypoint.sh
RUN chmod +x /usr/local/bin/api-entrypoint.sh && useradd --uid 10001 --create-home kurier && chown -R kurier /app
USER kurier
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=12 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"
ENTRYPOINT ["api-entrypoint.sh"]
