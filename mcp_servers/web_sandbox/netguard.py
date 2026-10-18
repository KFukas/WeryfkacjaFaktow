"""Bezpieczne pobieranie HTTP: ochrona SSRF, limity rozmiaru/czasu, allowlista Content-Type.

Kluczowe właściwości:
* tylko http/https, bez danych logowania w URL, tylko porty 80/443 (wyjątki wyłącznie z `SANDBOX_TEST_ALLOW`);
* adres IP sprawdzany **w chwili łączenia** (własny backend sieciowy httpcore) — to ten sam adres, z którym
  faktycznie nawiązujemy połączenie, więc DNS rebinding (inna odpowiedź DNS przy sprawdzeniu i przy łączeniu)
  nie działa;
* przekierowania obsługiwane ręcznie (≤ 3), każdy skok walidowany od nowa;
* ignorujemy proxy ze zmiennych środowiskowych (proxy ominęłoby sprawdzanie adresów);
* limit bajtów liczony po dekompresji (ochrona przed bombą gzip), twardy deadline całego pobrania.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

from mcp_servers.web_sandbox.settings import SandboxSettings

ALLOWED_CONTENT_TYPES = {
    "text/html": "html",
    "application/xhtml+xml": "html",
    "text/plain": "text",
    "application/json": "json",
    "application/ld+json": "json",
    "application/vnd.api+json": "json",
    "application/pdf": "pdf",
}
# Adresy zablokowane bezwarunkowo — nawet jeśli ktoś wpisze je do SANDBOX_TEST_ALLOW.
HARD_DENY = {ipaddress.ip_address("169.254.169.254"), ipaddress.ip_address("fd00:ec2::254"),
             ipaddress.ip_address("100.100.100.200")}


class FetchError(Exception):
    """Błąd pobrania z kodem do raportowania (bez szczegółów wewnętrznych)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class SSRFBlocked(FetchError):
    def __init__(self, message: str):
        super().__init__("ssrf_blocked", message)


Resolver = Callable[[str, int], list[str]]


def default_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(info[4][0] for info in infos))


def ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip in HARD_DENY:
        return False
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


@dataclass
class Guard:
    """Polityka sieciowa współdzielona przez walidację URL i backend łączący."""

    settings: SandboxSettings
    resolver: Resolver = default_resolver
    connections: list[tuple[str, str, int]] = field(default_factory=list)  # (host, ip, port) — do testów/audytu

    def _test_allowed(self, host: str, port: int) -> bool:
        return (host.lower(), port) in self.settings.test_allow

    def check_ip(self, host: str, ip_str: str, port: int) -> None:
        ip = ipaddress.ip_address(ip_str.split("%")[0])
        if ip in HARD_DENY:
            raise SSRFBlocked(f"adres metadanych chmury {ip} jest zablokowany")
        if ip_is_public(ip):
            return
        if self._test_allowed(host, port) or self._test_allowed(str(ip), port):
            return
        raise SSRFBlocked(f"adres {ip} (host {host}) nie jest publiczny")

    def validate_url(self, url: str) -> tuple[str, int]:
        if len(url) > 4000:
            raise FetchError("invalid_url", "URL jest zbyt długi")
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https"):
            raise SSRFBlocked(f"schemat „{scheme or '(brak)'}” jest niedozwolony — tylko http/https")
        if parts.username or parts.password:
            raise SSRFBlocked("dane logowania w URL są niedozwolone")
        host = (parts.hostname or "").lower()
        if not host:
            raise FetchError("invalid_url", "brak hosta w URL")
        try:
            port = parts.port or (443 if scheme == "https" else 80)
        except ValueError as exc:
            raise FetchError("invalid_url", "nieprawidłowy port") from exc
        if port not in self.settings.allowed_ports and not self._test_allowed(host, port):
            raise SSRFBlocked(f"port {port} jest niedozwolony")
        try:  # literał IP — sprawdzamy od razu (resolver i tak sprawdzi ponownie przy łączeniu)
            self.check_ip(host, str(ipaddress.ip_address(host)), port)
        except ValueError:
            pass
        if host in ("localhost", "localhost.localdomain") or host.endswith((".localhost", ".internal", ".local")):
            if not self._test_allowed(host, port):
                raise SSRFBlocked(f"host {host} jest lokalny")
        return host, port

    def resolve_checked(self, host: str, port: int) -> str:
        try:
            ips = self.resolver(host, port)
        except OSError as exc:
            raise FetchError("dns_error", f"nie można rozwiązać nazwy {host}") from exc
        if not ips:
            raise FetchError("dns_error", f"brak adresów dla {host}")
        for ip in ips:  # ścisło: jeśli KTÓRYKOLWIEK adres jest prywatny — odmowa
            self.check_ip(host, ip, port)
        return ips[0]


class GuardedBackend(httpcore.SyncBackend):
    """Backend httpcore, który rozwiązuje DNS sam i łączy się wyłącznie ze sprawdzonym adresem IP."""

    def __init__(self, guard: Guard):
        super().__init__()
        self.guard = guard

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):  # noqa: ANN001
        ip = self.guard.resolve_checked(host, port)
        self.guard.connections.append((host, ip, port))
        # TLS (SNI, weryfikacja certyfikatu) nadal używa nazwy hosta — httpcore robi start_tls z oryginalnym hostem.
        return super().connect_tcp(ip, port, timeout=timeout, local_address=local_address,
                                   socket_options=socket_options)


def build_client(guard: Guard) -> httpx.Client:
    timeout = httpx.Timeout(guard.settings.timeout_s, connect=min(5.0, guard.settings.timeout_s))
    transport = httpx.HTTPTransport(retries=0)
    transport._pool = httpcore.ConnectionPool(  # noqa: SLF001 — podmiana backendu sieciowego
        ssl_context=httpx.create_ssl_context(),
        max_connections=4,
        network_backend=GuardedBackend(guard),
    )
    return httpx.Client(transport=transport, timeout=timeout, follow_redirects=False, trust_env=False,
                        headers={"User-Agent": guard.settings.user_agent,
                                 "Accept": "text/html,application/xhtml+xml,application/json,text/plain,application/pdf",
                                 "Accept-Encoding": "gzip, deflate"})


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    kind: str  # html | text | json | pdf
    body: bytes
    encoding: str
    redirects: list[str]
    elapsed_ms: int


def safe_fetch(url: str, settings: SandboxSettings, guard: Guard | None = None,
               accept: set[str] | None = None) -> FetchResult:
    guard = guard or Guard(settings)
    allowed_kinds = accept or set(ALLOWED_CONTENT_TYPES.values())
    started = time.monotonic()
    deadline = started + settings.timeout_s * 1.5
    current = url
    redirects: list[str] = []
    with build_client(guard) as client:
        for _hop in range(settings.max_redirects + 1):
            guard.validate_url(current)
            try:
                with client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location", "")
                        if not location:
                            raise FetchError("bad_redirect", "przekierowanie bez nagłówka Location")
                        nxt = urljoin(current, location)
                        redirects.append(nxt)
                        current = nxt
                        continue
                    if resp.status_code >= 400:
                        raise FetchError("http_error", f"serwer zwrócił status {resp.status_code}")
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    kind = ALLOWED_CONTENT_TYPES.get(ctype)
                    if kind is None or kind not in allowed_kinds:
                        raise FetchError("unsupported_content_type", f"Content-Type „{ctype or '(brak)'}” jest niedozwolony")
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > settings.max_bytes:
                        raise FetchError("too_large", f"odpowiedź większa niż {settings.max_bytes} B")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if total > settings.max_bytes:
                            raise FetchError("too_large", f"odpowiedź większa niż {settings.max_bytes} B")
                        if time.monotonic() > deadline:
                            raise FetchError("timeout", "przekroczono łączny czas pobierania")
                        chunks.append(chunk)
                    return FetchResult(
                        url=url, final_url=current, status=resp.status_code, content_type=ctype, kind=kind,
                        body=b"".join(chunks), encoding=resp.charset_encoding or "utf-8", redirects=redirects,
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                    )
            except httpx.TimeoutException as exc:
                raise FetchError("timeout", "przekroczono limit czasu") from exc
            except httpx.TooManyRedirects as exc:  # pragma: no cover - obsługujemy ręcznie
                raise FetchError("too_many_redirects", "zbyt wiele przekierowań") from exc
            except httpx.HTTPError as exc:
                cause = exc.__cause__ or exc.__context__
                if isinstance(cause, FetchError):
                    raise cause from None
                raise FetchError("network_error", f"błąd sieci: {type(exc).__name__}") from exc
        raise FetchError("too_many_redirects", f"więcej niż {settings.max_redirects} przekierowania")
