# Metodologia: ocena wiarygodności i reguły werdyktu

Celem jest **powtarzalność i przejrzystość**: ta sama strona dostaje tę samą ocenę, a każdy punkt da się wytłumaczyć
redaktorowi (panel „Pokaż rozpisanie oceny”).

## 1. Twierdzenia
Twierdzenie to atomowy, sprawdzalny fakt, będący dosłownym fragmentem artykułu (z offsetami). Kategorie: liczbowe,
datowe, cytat, przyczynowe, porównawcze, inne. Opinie, prognozy i ogólniki nie są weryfikowane.

## 2. Ocena źródła (0–100)
```
wynik = clamp( część deterministyczna + korekta modelu (±15) + korroboracja (0…+10), 0, 100 )
```

### 2.1 Część deterministyczna (`score_source`, `config/credibility_rubric.yaml`)
**Typ źródła — wyłącznie z domeny:**

| Typ | Punkty | Pierwotne? |
|---|---|---|
| urząd statystyczny / bank centralny (stat.gov.pl, bdl.stat.gov.pl, nbp.pl, Eurostat) | 85 | tak |
| rejestr publiczny (KRS, ISAP) | 85 | tak |
| dane pierwotne (dane.gov.pl) | 80 | tak |
| administracja publiczna (gov.pl, sejm.gov.pl), organizacja międzynarodowa (europa.eu, nato.int, OECD, WHO) | 75 | tak |
| instytucja naukowa (nobelprize.org, PAN, uczelnie, DOI) | 70 | nie |
| media o ustalonej renomie | 60 | nie |
| encyklopedia (Wikipedia, Wikidata) | 50 | nie |
| inne media / nieznane / blog / forum / social media | 45 / 30 / 25 / 15 / 10 | nie |

**Modyfikatory:** pierwotne +5 · wtórne (encyklopedia, media) −5 · data publikacji +3 · autor/instytucja +2 ·
metodologia +5 · dane z oficjalnego API +5 · brak HTTPS −10 · nieaktualne względem okresu twierdzenia −5 ·
wydawca jest podmiotem twierdzenia (konflikt interesów) −10.

**Kary:** flagi injection high −25 / medium −8 / low −2 (łącznie maks. −45) · treść ukryta sprzeczna z widoczną −20 ·
samozwańcza wiarygodność −15 · domena-podróbka −40 (i typ „nieznane”).

**Zasada:** tekst strony nie może podnieść własnej oceny. Deklaracja „oficjalne źródło GUS” na nieznanej domenie
daje karę, a nie premię.

### 2.2 Korekta modelu (±15)
Model w etapie werdyktu może skorygować ocenę z uzasadnieniem (np. dane nieaktualne, źródło wtórne). Orkiestrator
przycina wartość do ±15 i **zeruje dodatnią korektę** dla źródeł z flagami medium/high.

### 2.3 Korroboracja
+5 za każde kolejne **niezależne** źródło (inna grupa wydawcy) o tej samej relacji do twierdzenia, maks. +10.
Grupy niezależności z rubryki: np. Wikipedia + Wikidata = `wikimedia`; strona GUS + API BDL = `gus`.

## 3. Relacja źródła do twierdzenia
- **supports** — cytat wprost potwierdza (ta sama wartość/data dla tego samego faktu i okresu),
- **contradicts** — cytat wprost przeczy (inna wartość/data dla tego samego faktu i okresu),
- **context** — źródło dotyczy tematu, ale nie rozstrzyga (lub jest wewnętrznie niejednoznaczne).

Relacja rozstrzygająca (supports/contradicts) wymaga **dosłownego cytatu** zweryfikowanego w tekście źródła; bez niego
źródło traktujemy jako kontekst.

## 4. Reguły werdyktu (`orchestrator/verdict_rules.py`)
Źródła z flagą injection **high** lub domeną-podróbką nie kwalifikują się jako podstawa werdyktu.

| Werdykt | Warunek |
|---|---|
| **potwierdzone** | ≥1 źródło **pierwotne** o wyniku **≥ 70** wspiera **albo** ≥2 **niezależne** źródła **≥ 60** wspierają; **i** żadne źródło ≥ 60 nie przeczy |
| **fałszywe** | wiarygodne źródło (**≥ 70**) bezpośrednio przeczy (i nie ma równie mocnego źródła pierwotnego „za”) |
| **wątpliwe** | wszystko pozostałe: brak danych, sprzeczne źródła, tylko słabe źródła, źródła z flagami |

Model proponuje werdykt; **końcowy werdykt = werdykt reguł, jeśli model się zgadza, w przeciwnym razie „wątpliwe”**
(z adnotacją w uzasadnieniu). Pewność jest ograniczana przez siłę dowodów (np. ≤ 0,6 dla „wątpliwe”, 0,85–0,97 dla
werdyktów rozstrzygających zależnie od liczby niezależnych podstaw).

Redaktor ma ostatnie słowo: decyzja w panelu nadpisuje werdykt agenta (historia zachowana).

## 5. Przykłady (dane offline)
| Twierdzenie | Źródła (ocena) | Werdykt |
|---|---|---|
| „…stopa bezrobocia rejestrowanego … na koniec grudnia 2023 r. wyniosła 5,1%.” | GUS BDL 60270 (100, supports), stat.gov.pl (100, supports) | potwierdzone |
| „Liczba ludności Polski na koniec 2023 r. przekroczyła 40 milionów.” | GUS: 37 636,5 tys. (100, contradicts) | fałszywe |
| „Do NATO Polska wstąpiła w 2001 roku.” | gov.pl/MON: 12 marca 1999 r. (85, contradicts) | fałszywe |
| „Ludność całej Unii Europejskiej na początku 2024 r. wynosiła około 449 mln osób.” | Eurostat tps00001: 449 489 862 (100, supports) | potwierdzone |
| „Średni kurs euro … NBP 2 stycznia 2024 r. wyniósł 4,3434 zł.” | NBP tabela 001/A/NBP/2024 (100, supports) | potwierdzone |
| „Wisła ma długość 1047 km.” | Wikipedia: 1022 km, dawniej 1047 km (50, context) | wątpliwe |
| „Mikołaj Kopernik urodził się w 1473 r. w Toruniu.” | tylko Wikipedia (50, supports) | wątpliwe (brak źródła ≥ progu) |
| „Maria Skłodowska-Curie otrzymała trzy Nagrody Nobla.” | nobelprize.org (80, contradicts), Wikipedia (55, contradicts) | fałszywe |
| „Wzrost cen był spowodowany wyłącznie podwyżkami cen energii.” | GUS — poziom inflacji (context) | wątpliwe |
| strona-podróbka „oficjalne źródło GUS” z ukrytym poleceniem | ocena 0, flagi high | nie może być podstawą → wątpliwe |

Więcej przykładów (w tym poprawna reakcja na prompt injection): `.claude/skills/weryfikacja-faktow/references/przyklady.md`.
