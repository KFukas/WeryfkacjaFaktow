"""Uruchamianie przebiegów agenta: w tle z API albo z linii poleceń.

  python -m orchestrator.runner --article 1             # pełna weryfikacja artykułu
  python -m orchestrator.runner --article 1 --claim 3   # ponowna weryfikacja jednego twierdzenia
  python -m orchestrator.runner --article 1 --llm anthropic
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
from typing import Any

from backend import services
from backend.config import get_settings
from backend.db import ensure_schema, session_scope
from orchestrator.llm.base import get_llm
from orchestrator.pipeline import PipelineConfig, run

ALLOWED_PROVIDERS = {"mock", "anthropic"}


def model_name(provider: str) -> str:
    return get_settings().anthropic_model if provider == "anthropic" else "mock-heuristic-1"


def create_run(article_id: int, claim_id: int | None = None, idempotency_key: str | None = None,
               provider: str | None = None) -> tuple[str, bool]:
    provider = provider or get_settings().llm_provider
    with session_scope() as db:
        if claim_id is not None:
            claim = services.get_claim(db, claim_id)
            if claim.article_id != article_id:
                raise services.DomainError("twierdzenie nie należy do artykułu")
        run_obj, created = services.create_run(db, article_id, claim_id, provider, model_name(provider),
                                               idempotency_key)
        if created and claim_id is not None:
            services.reset_claim(db, claim_id)
        return run_obj.id, created


async def execute(run_id: str, article_id: int, claim_id: int | None = None, provider: str | None = None,
                  llm: Any = None, **cfg_overrides: Any) -> dict:
    settings = get_settings()
    provider = provider or settings.llm_provider
    if llm is None:
        if provider == "anthropic" and not settings.anthropic_api_key:
            raise RuntimeError("LLM_PROVIDER=anthropic wymaga ANTHROPIC_API_KEY w .env")
        llm = get_llm(provider, settings)
    cfg = PipelineConfig.from_settings(settings, **cfg_overrides)
    return await run(run_id, article_id, llm, cfg, claim_id=claim_id)


def _thread_main(run_id: str, article_id: int, claim_id: int | None) -> None:
    try:
        asyncio.run(execute(run_id, article_id, claim_id))
    except Exception as exc:  # noqa: BLE001 — błąd przed połączeniem z newsroom: zapisujemy bezpośrednio
        from backend import schemas

        with session_scope() as db:
            services.log_agent_event(db, run_id, schemas.AgentEventIn(
                type="run_finished", payload={"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:2000]}))


def start_background(run_id: str, article_id: int, claim_id: int | None = None) -> threading.Thread:
    t = threading.Thread(target=_thread_main, args=(run_id, article_id, claim_id), daemon=True,
                         name=f"agent-run-{run_id[:8]}")
    t.start()
    return t


def main() -> int:
    p = argparse.ArgumentParser(description="Weryfikacja artykułu przez agenta")
    p.add_argument("--article", type=int, required=True)
    p.add_argument("--claim", type=int, default=None)
    p.add_argument("--llm", choices=sorted(ALLOWED_PROVIDERS), default=None)
    args = p.parse_args()
    ensure_schema()
    run_id, _ = create_run(args.article, args.claim, provider=args.llm)
    summary = asyncio.run(execute(run_id, args.article, args.claim, provider=args.llm))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("status") == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
