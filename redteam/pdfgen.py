"""Minimalny generator PDF (bez zależności) do spreparowanych dokumentów testowych.

Każdy fragment tekstu ma kolor wypełnienia i tryb renderowania — pozwala zbudować PDF z białym lub
niewidocznym (Tr 3) tekstem, który sanitizer musi wykryć. Tylko ASCII (czcionka Helvetica, WinAnsi).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Run:
    text: str
    color: tuple[float, float, float] = (0, 0, 0)
    render_mode: int = 0  # 3 = niewidoczny
    size: float = 12


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(runs: list[Run], title: str = "", extra_catalog: str = "") -> bytes:
    lines = []
    y = 780
    for r in runs:
        lines.append(f"BT /F1 {r.size:g} Tf {r.color[0]:g} {r.color[1]:g} {r.color[2]:g} rg {r.render_mode} Tr "
                     f"72 {y} Td ({_esc(r.text)}) Tj ET")
        y -= 20
    stream = "\n".join(lines).encode("latin-1")
    objs = [
        f"<< /Type /Catalog /Pages 2 0 R {extra_catalog}>>".encode(),
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 5 0 R >> >> "
        b"/Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        f"<< /Title ({_esc(title)}) /Producer (redteam-pdfgen) >>".encode("latin-1"),
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info {len(objs)} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
