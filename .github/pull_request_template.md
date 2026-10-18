## Co zmienia ten PR?


## Typ zmiany
- [ ] feat — nowa funkcja
- [ ] fix — poprawka
- [ ] test — testy / przypadki red-team
- [ ] docs — dokumentacja
- [ ] ci / chore

## Lista kontrolna
- [ ] `pytest` przechodzi lokalnie (w tym `tests/redteam`)
- [ ] `ruff check .` bez błędów
- [ ] Frontend: `npm run typecheck && npm test && npm run build` (jeśli dotyczy)
- [ ] Brak sekretów w diffie (`git diff --cached` sprawdzony)
- [ ] Zmiana w strefie nieufnej (sandbox) ma test negatywny
- [ ] Zaktualizowano dokumentację (`docs/`) i `CHANGELOG.md`
- [ ] Decyzja architektoniczna dopisana do `docs/DECYZJE.md` (jeśli dotyczy)

## Wpływ na bezpieczeństwo
Czy zmiana dotyka granicy zaufania (sandbox ↔ orkiestrator ↔ newsroom)? Jak to przetestowano?
