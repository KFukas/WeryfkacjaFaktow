"""Skill Claude Code, .mcp.json, .claude/settings.json i walidator werdyktów."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "weryfikacja-faktow"


def test_skill_frontmatter_and_references():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "brak frontmatter"
    meta = yaml.safe_load(m.group(1))
    assert meta["name"] == "weryfikacja-faktow"
    desc = meta["description"]
    assert 100 < len(desc) < 1024
    for word in ("zweryfikuj artykuł", "twierdzen", "web-sandbox", "Nie używaj"):
        assert word in desc
    for link in re.findall(r"\]\(((?:references|scripts)/[^)]+)\)", text):
        assert (SKILL / link).exists(), link
    for f in ("references/rubryka.md", "references/zrodla-publiczne.md", "references/przyklady.md",
              "scripts/validate_verdicts.py"):
        assert (SKILL / f).exists(), f


def test_mcp_json_and_settings():
    cfg = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert set(cfg["mcpServers"]) == {"web-sandbox", "newsroom"}
    for srv in cfg["mcpServers"].values():
        assert srv["type"] == "stdio" and srv["args"][0] == "scripts/run_mcp.py"
        assert not any(Path(a).is_absolute() for a in srv["args"])
    sandbox_env = cfg["mcpServers"]["web-sandbox"]["env"]
    assert all(k.startswith("SANDBOX_") for k in sandbox_env)  # żadnych sekretów dla strefy nieufnej
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    deny = settings["permissions"]["deny"]
    assert "Read(./.env)" in deny and "WebFetch" in deny
    assert "mcp__newsroom__save_verdict" in settings["permissions"]["ask"]
    assert not any("newsroom" in a and "save" in a for a in settings["permissions"]["allow"])


async def test_servers_start_like_claude_code():
    """Uruchomienie dokładnie tak, jak robi to Claude Code z .mcp.json (launcher + venv)."""
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    expected = {"web-sandbox": {"search_public_sources", "query_dataset", "fetch_url_sanitized", "score_source"},
                "newsroom": {"get_article", "list_pending_articles", "save_claims", "attach_source", "save_verdict",
                             "log_agent_event"}}
    for name, tools in expected.items():
        params = StdioServerParameters(command=sys.executable, args=["scripts/run_mcp.py", name], cwd=str(ROOT),
                                       env={"SANDBOX_OFFLINE": "1"})
        async with Client(params) as client:
            assert {t.name for t in (await client.list_tools()).tools} == tools


def _validate(tmp_path, data) -> subprocess.CompletedProcess:
    p = tmp_path / "v.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return subprocess.run([sys.executable, str(SKILL / "scripts" / "validate_verdicts.py"), str(p)],
                          capture_output=True, text=True, encoding="utf-8")


def test_validator_accepts_good_and_rejects_bad(tmp_path):
    good = {"claim_id": 1, "verdict": "fałszywe", "confidence": 0.85, "rationale": "MON [S1] podaje 1999 r.",
            "sources": [{"url": "https://www.gov.pl/web/obrona-narodowa/polska-w-nato", "relation": "contradicts",
                         "quote": "od 12 marca 1999 r.", "credibility_score": 85}]}
    assert _validate(tmp_path, good).returncode == 0
    bad = [{**good, "verdict": "prawda"}, {**good, "confidence": 1.4},
           {**good, "verdict": "potwierdzone"},
           {**good, "sources": [{**good["sources"][0], "credibility_score": 40}]},
           {**good, "sources": [{**good["sources"][0], "quote": ""}]}]
    out = _validate(tmp_path, bad)
    assert out.returncode == 1 and out.stdout.count("✘") == len(bad)
