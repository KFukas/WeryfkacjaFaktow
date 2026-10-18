# Serwer spreparowanych stron red-team (tylko sieć wewnętrzna sandboksa, profil „redteam”).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /rt
RUN pip install "pyyaml>=6.0"
COPY redteam/__init__.py redteam/server.py ./redteam/
RUN mkdir -p /rt/redteam/logs && chown 65534:65534 /rt/redteam/logs
COPY redteam/pages ./redteam/pages
USER 65534:65534
EXPOSE 8899
# W kontenerze nasłuch na 0.0.0.0, ale port NIE jest publikowany na hosta.
CMD ["python", "-m", "redteam.server", "--host", "0.0.0.0", "--port", "8899"]
