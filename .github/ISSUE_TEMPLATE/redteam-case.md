---
name: Nowy przypadek red-team
about: Zgłoś nowy wektor ataku na agenta (prompt injection, SSRF, eksfiltracja…)
title: "[red-team] "
labels: security, red-team
---

## Wektor ataku
Krótko: jaką technikę wykorzystuje strona (np. tekst ukryty w `<svg><title>`, instrukcja w nagłówku PDF).

## Spreparowana strona
Minimalny HTML/PDF (lub opis). Nie wklejaj realnych danych osobowych ani działających adresów eksfiltracji.

```html

```

## Oczekiwane zachowanie
- Sanitizer powinien usunąć: …
- Sanitizer powinien oflagować (`injection_flags.type`): …
- Agent NIE może: (np. wywołać `save_verdict`, odwiedzić adresu z treści, zmienić werdyktu)

## Szkic pliku `*.expected.yaml`
```yaml
id:
title:
must_remove: []
must_flag: []
must_not_contain_in_text: []
agent:
  forbidden_verdicts: []
```

## Ocena wpływu
Co by się stało, gdyby atak się powiódł?
