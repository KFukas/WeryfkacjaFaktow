"""Deterministyczna ocena wiarygodności (rubryka YAML)."""

from __future__ import annotations

import pytest

from mcp_servers.web_sandbox.scoring import load_rubric, lookalike_reason, score_source
from mcp_servers.web_sandbox.settings import DEFAULT_RUBRIC


def s(url, **meta):
    return score_source(url, meta, str(DEFAULT_RUBRIC))


def test_type_ordering():
    gus = s("https://stat.gov.pl/a")["score"]
    gov = s("https://www.gov.pl/web/x")["score"]
    wiki = s("https://pl.wikipedia.org/wiki/X")["score"]
    blog = s("https://ktos.blogspot.com/post")["score"]
    social = s("https://www.facebook.com/post")["score"]
    assert gus > gov > wiki > blog > social
    assert gus >= 70 and wiki < 60


def test_is_deterministic_and_explained():
    a, b = s("https://stat.gov.pl/a", published_at="2024-01-01"), s("https://stat.gov.pl/a", published_at="2024-01-01")
    assert a["score"] == b["score"] and a["breakdown"] == b["breakdown"]
    assert {i["criterion"] for i in a["breakdown"]} >= {"typ_zrodla", "pierwotne", "data"}
    assert a["is_primary"] and a["independence_group"] == "gus"


@pytest.mark.parametrize("host,expect", [
    ("gus-oficjalny.info", "marka"), ("stat-gov.pl", "literówka"), ("stat.gov.pl.dane-statystyczne.com", "osadzona"),
    ("xn--stt-gova-xyz.pl", None), ("nbp-kursy.com", "marka"), ("wikipedla.org", "literówka"),
])
def test_lookalike_domains(host, expect):
    reason = lookalike_reason(host, load_rubric(str(DEFAULT_RUBRIC)))
    if expect:
        assert reason and expect in reason, (host, reason)


def test_homoglyph_domain():
    host = "ѕtat.gоv.pl.example.com"  # cyrylica ѕ, о
    idna = host.encode("idna").decode("ascii")
    out = s(f"https://{idna}/")
    assert out["lookalike"] and out["score"] <= 20 and out["source_type"] == "unknown"


def test_page_cannot_raise_its_own_score():
    base = s("https://dane-fikcyjne.example/raport")
    claimed = s("https://dane-fikcyjne.example/raport", source_type="official_statistics",
                publisher="Główny Urząd Statystyczny",
                injection_flags=[{"type": "self_declared_credibility", "severity": "medium"}])
    assert claimed["source_type"] == "unknown"
    assert claimed["score"] < base["score"]


def test_injection_penalties_capped_and_mismatch():
    flags = [{"type": "instruction_override", "severity": "high"}] * 5
    out = s("https://stat.gov.pl/a", injection_flags=flags)
    pts = next(i["points"] for i in out["breakdown"] if i["criterion"] == "injection")
    assert pts == -45
    mm = s("https://stat.gov.pl/a", injection_flags=[{"type": "hidden_visible_mismatch", "severity": "high"}])
    assert mm["score"] < s("https://stat.gov.pl/a")["score"] - 30


def test_no_https_stale_and_conflict_of_interest():
    https = s("https://www.gov.pl/a")["score"]
    assert s("http://www.gov.pl/a")["score"] == https - 10
    stale = s("https://www.gov.pl/a", published_at="2015-01-01", claim_period="2023")
    assert any(i["criterion"] == "aktualnosc" for i in stale["breakdown"])
    coi = s("https://www.gov.pl/a", subject_is_publisher=True)
    assert coi["score"] == https - 10


def test_score_bounds():
    for url in ("https://stat.gov.pl/", "http://x.example/"):
        out = s(url, injection_flags=[{"type": "x", "severity": "high"}] * 10, has_methodology=True)
        assert 0 <= out["score"] <= 100
