"""SSRF, przekierowania, DNS rebinding, limity rozmiaru/czasu i Content-Type."""

from __future__ import annotations

import ipaddress
from dataclasses import replace

import pytest

from mcp_servers.web_sandbox.netguard import FetchError, Guard, SSRFBlocked, ip_is_public, safe_fetch
from mcp_servers.web_sandbox.settings import SandboxSettings
from mcp_servers.web_sandbox.tools import SandboxTools


def _settings(port: int | None = None, **kw) -> SandboxSettings:
    allow = frozenset({("127.0.0.1", port)}) if port else frozenset()
    base = SandboxSettings(offline=False, timeout_s=2.0, test_allow=allow)
    return replace(base, **kw)


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/x", "gopher://127.0.0.1:70/", "data:text/html,<b>x</b>",
    "javascript:alert(1)", "http://user:pass@example.com/", "http://example.com:8080/", "https://example.com:22/",
    "http://localhost/", "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/", "http://[::1]/",
    "http://10.0.0.5/", "http://192.168.1.1/", "http://172.16.0.1/", "http://100.64.0.1/", "http://0.0.0.0/",
    "http://[::ffff:127.0.0.1]/", "http://metadata.internal/", "http://printer.local/",
])
def test_blocked_urls(url):
    tools = SandboxTools(_settings())
    out = tools.fetch_url_sanitized(url)
    assert out.get("error") in ("ssrf_blocked", "invalid_url"), out


def test_ip_classification():
    assert ip_is_public(ipaddress.ip_address("93.184.216.34"))
    for ip in ("127.0.0.1", "10.1.2.3", "169.254.169.254", "::1", "fe80::1", "fc00::1", "224.0.0.1",
               "::ffff:10.0.0.1", "100.64.1.1", "0.0.0.0", "255.255.255.255"):
        assert not ip_is_public(ipaddress.ip_address(ip)), ip


def test_metadata_ip_blocked_even_if_allowlisted():
    s = replace(SandboxSettings(offline=False), test_allow=frozenset({("169.254.169.254", 80)}))
    with pytest.raises(SSRFBlocked):
        Guard(s).validate_url("http://169.254.169.254/")


def test_hostname_resolving_to_private_ip_is_blocked():
    guard = Guard(_settings(), resolver=lambda host, port: ["10.0.0.7"])
    with pytest.raises(SSRFBlocked):
        safe_fetch("http://intranet.example.com/", guard.settings, guard)


def test_any_private_address_in_dns_answer_blocks():
    guard = Guard(_settings(), resolver=lambda host, port: ["93.184.216.34", "127.0.0.1"])
    with pytest.raises(SSRFBlocked):
        guard.resolve_checked("mixed.example.com", 80)


def test_dns_rebinding_is_checked_at_connect_time(http_server):
    """Pierwsze rozwiązanie DNS daje adres publiczny, drugie (przy łączeniu) — loopback. Musi być blokada."""
    port, hits = http_server
    answers = iter([["93.184.216.34"], ["127.0.0.1"], ["127.0.0.1"]])
    settings = replace(_settings(), allowed_ports=frozenset({80, 443, port}))
    guard = Guard(settings, resolver=lambda host, p: next(answers))
    assert guard.resolve_checked("rebind.example.com", port) == "93.184.216.34"  # „sprawdzenie” atakującego
    with pytest.raises(SSRFBlocked):
        safe_fetch(f"http://rebind.example.com:{port}/ok", settings, guard)
    assert hits == []  # żadne żądanie nie dotarło do serwera wewnętrznego


def test_connection_uses_validated_ip(http_server):
    port, hits = http_server
    settings = _settings(port)
    guard = Guard(settings)
    res = safe_fetch(f"http://127.0.0.1:{port}/ok", settings, guard)
    assert res.status == 200 and b"5,1%" in res.body
    assert guard.connections == [("127.0.0.1", "127.0.0.1", port)]


def test_redirect_to_metadata_blocked(http_server):
    port, hits = http_server
    out = SandboxTools(_settings(port)).fetch_url_sanitized(f"http://127.0.0.1:{port}/to-metadata")
    assert out["error"] == "ssrf_blocked"


def test_redirect_to_other_loopback_port_blocked(http_server):
    port, _ = http_server
    out = SandboxTools(_settings(port)).fetch_url_sanitized(f"http://127.0.0.1:{port}/to-loopback-other-port")
    assert out["error"] == "ssrf_blocked"


def test_redirect_to_file_scheme_blocked(http_server):
    port, _ = http_server
    out = SandboxTools(_settings(port)).fetch_url_sanitized(f"http://127.0.0.1:{port}/to-file")
    assert out["error"] == "ssrf_blocked"


def test_redirect_limit(http_server):
    port, hits = http_server
    tools = SandboxTools(_settings(port))
    assert tools.fetch_url_sanitized(f"http://127.0.0.1:{port}/loop0")["error"] == "too_many_redirects"
    assert len(hits) == 4  # 1 + 3 przekierowania, potem stop
    ok = tools.fetch_url_sanitized(f"http://127.0.0.1:{port}/chain2")
    assert "error" not in ok and ok["final_url"].endswith("/ok") and len(ok["redirects"]) == 2


@pytest.mark.parametrize("path,code", [
    ("/big", "too_large"), ("/big-nolength", "too_large"), ("/gzip-bomb", "too_large"),
    ("/image", "unsupported_content_type"), ("/exe", "unsupported_content_type"), ("/missing", "http_error"),
])
def test_limits_and_content_types(http_server, path, code):
    port, _ = http_server
    out = SandboxTools(_settings(port)).fetch_url_sanitized(f"http://127.0.0.1:{port}{path}")
    assert out["error"] == code, out


def test_total_deadline(http_server):
    port, _ = http_server
    settings = _settings(port, timeout_s=1.0)
    with pytest.raises(FetchError) as exc:
        safe_fetch(f"http://127.0.0.1:{port}/slow", settings)
    assert exc.value.code == "timeout"


def test_offline_mode_does_not_touch_network(http_server):
    port, hits = http_server
    tools = SandboxTools(replace(SandboxSettings(offline=True), allowed_ports=frozenset({80, 443, port})))
    out = tools.fetch_url_sanitized("https://example.com/not-in-archive")
    assert out["error"] == "offline_unavailable"
    assert hits == []


def test_envelope_shape_offline():
    out = SandboxTools(SandboxSettings(offline=True)).fetch_url_sanitized(
        "https://stat.gov.pl/obszary-tematyczne/ludnosc/ludnosc/")
    for key in ("url", "final_url", "fetched_at", "content_sha256", "title", "text", "untrusted",
                "injection_flags", "removed"):
        assert key in out
    assert out["untrusted"] is True and len(out["content_sha256"]) == 64
    assert "37 636,5" in out["text"]
