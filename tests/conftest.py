"""Wspólne fikstury: osobna baza SQLite na każdy test, klient HTTP, tryb offline."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("SANDBOX_OFFLINE", "1")


@pytest.fixture()
def db_url(tmp_path) -> str:
    return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture()
def engine(db_url):
    from backend import models  # noqa: F401
    from backend.db import Base, configure

    eng = configure(db_url)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    from backend.db import session_factory

    session = session_factory()()
    yield session
    session.close()


@pytest.fixture()
def client(engine):
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seeded(engine):
    from backend.seed import seed

    seed()
    return engine
