"""Lokalny serwer HTTP do testów SSRF/limitów (wątek, losowy port na 127.0.0.1)."""

from __future__ import annotations

import gzip
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class _Handler(BaseHTTPRequestHandler):
    hits: list[str] = []

    def log_message(self, *args):  # cisza w testach
        pass

    def _send(self, status=200, body=b"", ctype="text/html; charset=utf-8", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        if body is not None:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        _Handler.hits.append(self.path)
        p = self.path
        port = self.server.server_address[1]
        if p == "/ok":
            self._send(body="<html><body><p>Treść poprawna 5,1%.</p></body></html>".encode())
        elif p == "/to-metadata":
            self._send(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})
        elif p == "/to-loopback-other-port":
            self._send(302, headers={"Location": "http://127.0.0.1:1/admin"})
        elif p == "/to-file":
            self._send(302, headers={"Location": "file:///etc/passwd"})
        elif p.startswith("/loop"):
            n = int(p.removeprefix("/loop") or 0)
            self._send(302, headers={"Location": f"http://127.0.0.1:{port}/loop{n + 1}"})
        elif p == "/chain2":
            self._send(302, headers={"Location": f"http://127.0.0.1:{port}/chain1"})
        elif p == "/chain1":
            self._send(302, headers={"Location": f"http://127.0.0.1:{port}/ok"})
        elif p == "/big":
            self._send(body=b"<p>" + b"A" * (3 * 1024 * 1024) + b"</p>")
        elif p == "/big-nolength":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            for _ in range(40):
                self.wfile.write(b"B" * 100_000)
        elif p == "/gzip-bomb":
            payload = gzip.compress(b"0" * (20 * 1024 * 1024))
            self._send(body=payload, headers={"Content-Encoding": "gzip"})
        elif p == "/image":
            self._send(body=b"<html>fake image</html>", ctype="image/png")
        elif p == "/exe":
            self._send(body=b"MZ\x90\x00", ctype="application/octet-stream")
        elif p == "/slow":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            for _ in range(20):
                self.wfile.write(b"<p>x</p>")
                self.wfile.flush()
                time.sleep(0.3)
        else:
            self._send(404, body=b"brak")


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):  # klient zrywa połączenie przy limitach — to oczekiwane
        pass


@pytest.fixture()
def http_server():
    srv = _QuietServer(("127.0.0.1", 0), _Handler)
    _Handler.hits = []
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1], _Handler.hits
    srv.shutdown()
    srv.server_close()
