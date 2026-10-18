"""Skaner sekretów dla zmian w indeksie git (uruchamiany przed każdym pushem).

Użycie:  python scripts/check_secrets.py            # sprawdza `git diff --cached`
         python scripts/check_secrets.py --all      # sprawdza wszystkie śledzone pliki
Kod wyjścia 1 = znaleziono coś podejrzanego.
"""

from __future__ import annotations

import re
import subprocess
import sys

PATTERNS = {
    "klucz Anthropic": re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    "klucz OpenAI-podobny": re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    "token GitHub": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "klucz AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "klucz prywatny": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "przypisany sekret": re.compile(
        r"(?i)\b(ANTHROPIC_API_KEY|API_KEY|SECRET|PASSWORD|TOKEN)\s*[=:]\s*['\"]?(?!\$\{)([A-Za-z0-9_\-]{24,})"
    ),
}
FORBIDDEN_FILES = re.compile(r"(^|/)\.env$|(^|/)\.env\.(?!example$)[^/]+$")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout  # noqa: S603,S607


def main() -> int:
    check_all = "--all" in sys.argv
    problems: list[str] = []
    if check_all:
        files = _git("ls-files").splitlines()
        content = {f: open(f, encoding="utf-8", errors="ignore").read() for f in files}  # noqa: SIM115
    else:
        files = _git("diff", "--cached", "--name-only").splitlines()
        diff = _git("diff", "--cached", "-U0")
        added = "\n".join(line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
        content = {"(diff --cached)": added}
    for f in files:
        if FORBIDDEN_FILES.search(f):
            problems.append(f"plik z sekretami w indeksie: {f}")
    for name, text in content.items():
        for label, pattern in PATTERNS.items():
            for m in pattern.finditer(text):
                problems.append(f"{label} w {name}: …{m.group(0)[:12]}…")
    if problems:
        print("ZNALEZIONO POTENCJALNE SEKRETY:")
        for p in problems:
            print("  -", p)
        return 1
    print(f"OK — brak sekretów ({'wszystkie pliki' if check_all else 'zmiany w indeksie'}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
