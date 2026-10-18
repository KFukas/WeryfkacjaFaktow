# Strefa NIEUFNA: tylko kod sandboksa i rubryka. Brak backendu, orkiestratora, kluczy API i dostępu do bazy.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONIOENCODING=utf-8
WORKDIR /sandbox
RUN pip install "httpx>=0.27,<1" "lxml>=5.2" "lxml_html_clean>=0.4" "trafilatura>=1.12" "pypdf>=4.0" "pyyaml>=6.0" "mcp>=2.3,<3"
COPY mcp_servers/__init__.py ./mcp_servers/__init__.py
COPY mcp_servers/web_sandbox ./mcp_servers/web_sandbox
COPY config/credibility_rubric.yaml ./config/credibility_rubric.yaml
ENV SANDBOX_RUBRIC_PATH=/sandbox/config/credibility_rubric.yaml
# Użytkownik bez uprawnień; system plików tylko do odczytu ustawiany w docker-compose (read_only: true).
USER 65534:65534
EXPOSE 8765
CMD ["python", "-m", "mcp_servers.web_sandbox.server", "--http", "--host", "0.0.0.0", "--port", "8765"]
