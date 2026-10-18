"""Test e2e UI (Playwright) + zrzuty ekranu do dokumentacji.

Wymaga działającego API (:8000) i frontendu (:5173 w trybie dev albo :8080 w dockerze) oraz:
  pip install playwright && playwright install chromium
Użycie:  python scripts/ui_e2e.py [--url http://127.0.0.1:5173] [--screenshots docs/img]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:5173")
    p.add_argument("--screenshots", default="")
    p.add_argument("--article-title", default="Dwadzieścia lat Polski w Unii Europejskiej")
    args = p.parse_args()
    shots = Path(args.screenshots) if args.screenshots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 960}, locale="pl-PL")
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(args.url)
        expect(page.get_by_text("Kurier Faktów").first).to_be_visible()
        row = page.locator("li", has_text=args.article_title)
        expect(row).to_be_visible(timeout=15_000)
        if shots:
            page.screenshot(path=str(shots / "panel-redaktora.png"))

        row.get_by_role("button", name="Weryfikuj").click()
        expect(page.get_by_role("heading", name=args.article_title)).to_be_visible()
        expect(page.get_by_text("Przebieg").first).to_be_visible(timeout=15_000)
        if shots:
            page.wait_for_timeout(1500)
            page.screenshot(path=str(shots / "postep-na-zywo.png"))
        expect(page.get_by_text("Przebieg ")).to_have_count(0, timeout=240_000)  # przebieg zakończony
        nato = page.get_by_role("button", name="Twierdzenie: Fałszywe. Do NATO Polska wstąpiła w 2001 roku.")
        expect(nato).to_be_visible(timeout=180_000)
        expect(page.get_by_role("button", name="Twierdzenie: Potwierdzone. Polska przystąpiła do Unii Europejskiej 1 maja 2004 r.")).to_be_visible()
        nato.click()
        panel = page.get_by_role("complementary", name="Szczegóły twierdzenia")
        expect(panel.get_by_text("12 marca 1999").first).to_be_visible()
        expect(panel.get_by_text("Pokaż rozpisanie oceny").first).to_be_visible()
        panel.get_by_text("Pokaż rozpisanie oceny").first.click()
        if shots:
            page.screenshot(path=str(shots / "adnotacje-i-panel.png"))

        page.get_by_role("tab", name="Log agenta (audyt)").click()
        expect(page.get_by_role("cell", name="run_finished", exact=True)).to_be_visible(timeout=15_000)
        if shots:
            page.screenshot(path=str(shots / "audyt.png"))

        page.get_by_role("tab", name="Tekst z adnotacjami").click()
        page.get_by_role("button", name="Przełącz tryb jasny/ciemny").click()
        expect(page.locator("html.dark")).to_have_count(1)
        page.wait_for_timeout(600)  # koniec animacji kolorów
        if shots:
            page.screenshot(path=str(shots / "tryb-ciemny.png"))
        browser.close()
        if errors:
            print("Błędy JS:", errors)
            return 1
    print("UI e2e: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
