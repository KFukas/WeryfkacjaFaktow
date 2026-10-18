"""Serwer spreparowanych stron red-team (wyłącznie 127.0.0.1).

  python -m redteam.server [--port 8899]

* `/rt/<id>`  — strona przypadku (`redteam/pages/<id>.html|pdf`), z dyrektywami z `<id>.expected.yaml` (`serve`):
  przekierowania (SSRF), zły Content-Type, generowane bomby (ogromny HTML, głęboki DOM).
* `/collect`  — „odbiornik” eksfiltracji: niczego nie robi, ale każde żądanie trafia do logu.
* Każde żądanie jest zapisywane w `redteam/logs/requests.jsonl` — eval szuka tam tokenów-kanarków.
Znaczniki w stronach: `@@BASE@@` → adres serwera, `@@PORT@@` → port.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml

PAGES = Path(__file__).resolve().parent / "pages"
LOGS = Path(__file__).resolve().parent / "logs"


def load_cases() -> list[dict[str, Any]]:
    return [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(PAGES.glob("*.expected.yaml"))]


@dataclass
class RequestLog:
    path: Path | None = None
    entries: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, entry: dict[str, Any]) -> None:
        with self.lock:
            self.entries.append(entry)
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def clear(self) -> None:
        with self.lock:
            self.entries.clear()


def make_handler(log: RequestLog, cases: dict[str, dict[str, Any]]):
    class Handler(BaseHTTPRequestHandler):
        server_version = "redteam/1.0"

        def log_message(self, *args: Any) -> None:  # własny log JSONL
            pass

        def _base(self) -> str:
            host = self.headers.get("Host") or f"127.0.0.1:{self.server.server_address[1]}"
            return f"http://{host}"

        def _send(self, status: int, body: bytes = b"", ctype: str = "text/html; charset=utf-8",
                  headers: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _subst(self, text: str) -> str:
            port = str(self.server.server_address[1])
            return text.replace("@@BASE@@", self._base()).replace("@@PORT@@", port)

        def do_GET(self) -> None:  # noqa: N802
            parts = urlsplit(self.path)
            log.add({"ts": time.time(), "path": parts.path, "query": unquote(parts.query), "raw": self.path,
                     "host": self.headers.get("Host", ""), "ua": self.headers.get("User-Agent", "")})
            if parts.path.startswith("/collect"):
                return self._send(200, b"ok", "text/plain")
            if not parts.path.startswith("/rt/"):
                return self._send(404, b"brak")
            cid = parts.path.removeprefix("/rt/").strip("/")
            spec = cases.get(cid, {})
            serve = spec.get("serve", {})
            if "redirect" in serve:
                return self._send(302, headers={"Location": self._subst(serve["redirect"])})
            gen = serve.get("generate")
            if gen == "huge_html":
                body = b"<html><body><article><p>" + b"Raport " * 600_000 + b"</p></article></body></html>"
                return self._send(200, body)
            if gen == "deep_dom":
                inner = "<p>Raport gminy: dane w zagnieżdżonej strukturze.</p>"
                body = ("<html><body>" + "<div>" * 5000 + inner + "</div>" * 5000 + "</body></html>").encode()
                return self._send(200, body)
            file = PAGES / serve.get("file", f"{cid}.html")
            if not file.is_file() or file.parent != PAGES:
                return self._send(404, b"brak")
            ctype = serve.get("content_type") or ("application/pdf" if file.suffix == ".pdf" else "text/html; charset=utf-8")
            data = file.read_bytes()
            if file.suffix == ".html":
                data = self._subst(data.decode("utf-8")).encode("utf-8")
            return self._send(200, data, ctype)

    return Handler


class RedteamServer:
    def __init__(self, port: int = 8899, log_file: Path | None = None):
        self.cases = {c["id"]: c for c in load_cases()}
        self.log = RequestLog(log_file)
        handler = make_handler(self.log, self.cases)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)  # tylko localhost
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self._thread: threading.Thread | None = None

    def start(self) -> RedteamServer:
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True, name="redteam-server")
        self._thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def url(self, case: dict[str, Any]) -> str:
        host = case.get("host", "127.0.0.1")
        return f"http://{host}:{self.port}{case['path']}"


def main() -> None:
    p = argparse.ArgumentParser(description="Serwer stron red-team (tylko 127.0.0.1)")
    p.add_argument("--port", type=int, default=8899)
    args = p.parse_args()
    srv = RedteamServer(args.port, LOGS / "requests.jsonl")
    print(f"Serwer red-team: http://127.0.0.1:{srv.port}/rt/<id> — {len(srv.cases)} przypadków. Ctrl+C kończy.")
    try:
        srv.httpd.serve_forever()
    except KeyboardInterrupt:
        srv.stop()


if __name__ == "__main__":
    main()
