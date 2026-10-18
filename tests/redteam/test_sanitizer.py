"""Red-team (offline, deterministyczne): każdy przypadek z redteam/pages/*.expected.yaml przechodzi przez
prawdziwy serwer HTTP i `fetch_url_sanitized` — sanitizer musi usunąć/oflagować to, co opisuje plik expected."""

from __future__ import annotations

import pytest

from mcp_servers.web_sandbox.tools import SandboxTools
from redteam.harness import sandbox_settings
from redteam.server import RedteamServer, load_cases

CASES = load_cases()


@pytest.fixture(scope="module")
def server():
    srv = RedteamServer(port=0).start()
    yield srv
    srv.stop()


@pytest.fixture(scope="module")
def tools(server):
    return SandboxTools(sandbox_settings(server.port))


def test_catalog_has_at_least_20_cases():
    assert len(CASES) >= 20
    assert len({c["id"] for c in CASES}) == len(CASES)
    for c in CASES:
        assert {"id", "title", "vector", "path", "claim", "sanitizer", "agent"} <= set(c), c.get("id")


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_sanitizer_case(case, server, tools):
    exp = case["sanitizer"]
    env = tools.fetch_url_sanitized(server.url(case))
    if exp.get("expect_error"):
        assert env.get("error") == exp["expect_error"], env
        return
    assert "error" not in env, env
    flags = {f["type"] for f in env["injection_flags"]}
    missing = set(exp.get("must_flag", [])) - flags
    assert not missing, f"brak flag {missing}; są: {sorted(flags)}"
    for needle in exp.get("must_not_contain_in_text", []):
        assert needle not in env["text"] and needle not in env["title"], f"w tekście zostało: {needle!r}"
    for needle in exp.get("must_contain_in_text", []):
        assert needle in env["text"], f"brak w tekście: {needle!r}"
    for key, minimum in (exp.get("min_removed") or {}).items():
        assert env["removed"][key] >= minimum, (key, env["removed"])
    assert env["untrusted"] is True
    if "score" in exp:
        score = tools.score_source(env["final_url"], {"injection_flags": env["injection_flags"],
                                                      "publisher_claimed": env["metadata"].get("publisher_claimed")})
        assert score["score"] <= exp["score"]["max"], score
        assert bool(score["lookalike"]) == exp["score"]["lookalike"]


def test_multistage_page_b_never_requested_by_sanitizer(server, tools):
    server.log.clear()
    case = next(c for c in CASES if c["id"] == "rt28")
    tools.fetch_url_sanitized(server.url(case))
    assert [e["path"] for e in server.log.entries] == ["/rt/rt28"]  # sandbox nie podąża za linkami z treści


def test_benign_fixture_pages_have_no_false_positives():
    """Strony łagodne (archiwum offline) nie mogą dostawać flag medium/high — miara fałszywych alarmów."""
    from mcp_servers.web_sandbox.providers import FIXTURES, Providers
    from mcp_servers.web_sandbox.settings import SandboxSettings

    t = SandboxTools(SandboxSettings(offline=True))
    urls = [d["url"] for d in Providers(t.settings)._index() if d.get("page")]
    assert len(urls) >= 10 and (FIXTURES / "pages").is_dir()
    for url in urls:
        env = t.fetch_url_sanitized(url)
        bad = [f for f in env["injection_flags"] if f["severity"] in ("high", "medium")]
        assert not bad, (url, bad)
