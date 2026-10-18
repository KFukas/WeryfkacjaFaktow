# Weryfikacja faktów — „Kurier Faktów”

Agent AI dla fikcyjnej redakcji serwisu informacyjnego **„Kurier Faktów”** (nazwa fikcyjna). Agent:

1. rozbija tekst artykułu na pojedyncze, weryfikowalne twierdzenia,
2. wyszukuje źródła w publicznych danych (GUS BDL, Eurostat, NBP, KRS, dane.gov.pl, Wikipedia/Wikidata),
3. ocenia wiarygodność każdego źródła (transparentna rubryka 0–100),
4. oznacza twierdzenie jako **potwierdzone**, **wątpliwe** lub **fałszywe** — z uzasadnieniem, cytatem i poziomem pewności.

**Wyróżnik:** strony WWW są traktowane jako NIEUFNE. Pobieranie odbywa się w izolowanym serwerze MCP
(`mcp-web-sandbox`) z ochroną SSRF i oczyszczaniem treści, a repozytorium zawiera zestaw spreparowanych
stron red-team sprawdzających odporność agenta na prompt injection.

> Projekt w budowie — dokumentacja zostanie uzupełniona w kolejnych kamieniach milowych (zob. `CHANGELOG.md`).

## Licencja
MIT — zob. [LICENSE](LICENSE).
