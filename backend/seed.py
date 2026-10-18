"""Dane przykładowe: fikcyjne artykuły „Kuriera Faktów” z twierdzeniami prawdziwymi, fałszywymi i niejednoznacznymi.

Uruchomienie:  python -m backend.seed [--reset]
Redakcja, autorzy i cytowane osoby z Fikcyjnowa są fikcyjne. Fakty statystyczne i historyczne są realne
(lub celowo przekłamane — zob. komentarze `# oczekiwany werdykt`), żeby agent miał co weryfikować.
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from backend.db import Base, get_engine, session_scope
from backend.models import Article

ARTICLES: list[dict[str, str]] = [
    {
        "title": "Rynek pracy i ceny w 2023 roku — podsumowanie",
        "author": "Anna Przykładowa",
        "body": (
            "Miniony rok przyniósł wyraźne zmiany w gospodarce. "
            # potwierdzone (GUS)
            "Według GUS stopa bezrobocia rejestrowanego w Polsce na koniec grudnia 2023 r. wyniosła 5,1%. "
            # potwierdzone (GUS)
            "Średnioroczna inflacja w 2023 r. wyniosła 11,4%. "
            # fałszywe (GUS: ok. 37,6 mln)
            "Liczba ludności Polski na koniec 2023 r. przekroczyła 40 milionów. "
            # wątpliwe (twierdzenie przyczynowe, brak źródła)
            "Wzrost cen był spowodowany wyłącznie podwyżkami cen energii. "
            "Ekonomiści spodziewają się, że kolejne lata przyniosą stabilizację."
        ),
    },
    {
        "title": "Dwadzieścia lat Polski w Unii Europejskiej",
        "author": "Piotr Testowy",
        "body": (
            "Członkostwo we wspólnocie zmieniło kraj nie do poznania. "
            # potwierdzone
            "Polska przystąpiła do Unii Europejskiej 1 maja 2004 r. "
            # fałszywe (12 marca 1999 r.)
            "Do NATO Polska wstąpiła w 2001 roku. "
            # potwierdzone (Eurostat ~449,2 mln)
            "Ludność całej Unii Europejskiej na początku 2024 r. wynosiła około 449 mln osób. "
            "Wielu mieszkańców podkreśla, że najważniejsza jest swoboda podróżowania."
        ),
    },
    {
        "title": "Od Tatr po Bałtyk: geografia w liczbach",
        "author": "Katarzyna Fikcyjna",
        "body": (
            "Polska geografia potrafi zaskoczyć. "
            # potwierdzone (rocznik GUS)
            "Najwyższym szczytem Polski są Rysy o wysokości 2499 m n.p.m. "
            # wątpliwe (źródła podają 1022 km i 1047 km)
            "Wisła ma długość 1047 km. "
            # wątpliwe (brak danych o fikcyjnej spółce)
            "Spółka Wodociągi Fikcyjnowskie odnotowała w 2023 r. rekordowy zysk 12 mln zł. "
            "Warto odwiedzić oba krańce kraju jeszcze w tym sezonie."
        ),
    },
    {
        "title": "Bohaterowie polskiej nauki",
        "author": "Jan Wzorcowy",
        "body": (
            "Polscy uczeni od wieków zmieniali świat. "
            # wątpliwe/potwierdzone w zależności od źródeł (tylko encyklopedia offline → wątpliwe)
            "Mikołaj Kopernik urodził się w 1473 r. w Toruniu. "
            # fałszywe (dwie nagrody: 1903 i 1911)
            "Maria Skłodowska-Curie otrzymała trzy Nagrody Nobla. "
            # wątpliwe (cytat nieweryfikowalny)
            "Jak powiedział nam prof. Jan Nowak z Uniwersytetu w Fikcyjnowie, polska nauka nigdy nie była silniejsza. "
            "Ich dorobek inspiruje kolejne pokolenia badaczy."
        ),
    },
]


def seed(reset: bool = False) -> int:
    Base.metadata.create_all(get_engine())
    created = 0
    with session_scope() as db:
        if reset:
            for art in db.scalars(select(Article)):
                db.delete(art)
            db.flush()
        existing = {a.title for a in db.scalars(select(Article))}
        for data in ARTICLES:
            if data["title"] not in existing:
                db.add(Article(**data))
                created += 1
    return created


if __name__ == "__main__":
    n = seed(reset="--reset" in sys.argv)
    print(f"Dodano {n} artykułów przykładowych.")
