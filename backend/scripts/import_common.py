"""Shared helpers of the source importers (scripts/import_*.py).

Importers print a seed JSON list `[{"meta": InnovationMeta}, ...]` for scripts/upload_innovations.py.
Classification here is deliberately keyword-based and deterministic, so every label can be
explained (the brief asks for transparent criteria). Admins correct labels in "Dokumenty".
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.knowledge.schemas import InnovationMeta  # noqa: E402
from app.modules.knowledge.taxonomy import Category, InnovationType, InstitutionType  # noqa: E402

# Polite identification for public open-data endpoints.
USER_AGENT = "radar-innowacji-importer/1.0 (+https://pcinn.org)"

# Word-prefix keywords per sector (Polish, then English for EU records), matched on diacritic-free lowercase text.
# shortcut: keyword lists miss synonyms; replace with the GLiDE classifier when imports grow.
SECTOR_KEYWORDS: dict[Category, tuple[str, ...]] = {
    Category.AUTOMOTIVE: ("motoryzac", "samochod", "pojazd", "elektromobil", "transport", "drog", "akumulator", "silnik",
                          "mobilnosc", "kolej", "rower", "vehicle", "automotive", "batter", "mobility", "railway"),
    Category.AVIATION: ("lotnic", "samolot", "dron", "bezzalogow", "aero", "awionik", "lotnisk", "smiglowc", "aircraft", "aviation", "drone", "airport"),
    Category.SPACE: ("kosmicz", "satelit", "orbit", "astronom", "obserwacji ziemi", "teledetekc", "satellite", "space ", "earth observation"),
    Category.ICT: ("informaty", "cyfrow", "algorytm", "sztuczn", "uczenie maszyn", "oprogramowan", "dane ", "internet",
                   "siec", "elektroni", "komputer", "aplikac", "cyberbezpiecz", "robot", "automaty", "e-uslug", "digital", "software",
                   "artificial intelligence", "machine learning", "cyber", "computing", "quantum"),
    Category.QUALITY_OF_LIFE: ("zdrow", "medycy", "leczen", "choro", "pacjent", "terapi", "klimat", "srodowisk", "energi",
                               "woda", "wody", "powietrz", "zywno", "rolnic", "edukac", "szkol", "spolecz", "senior",
                               "bezpieczen", "ratown", "turyst", "kultur", "dziedzict", "przyrod", "ekolog", "odpad",
                               "health", "medical", "patient", "disease", "climate", "energy", "water", "food",
                               "agricult", "education", "social", "citizen", "heritage", "waste", "environment"),
}
TYPE_KEYWORDS: list[tuple[InnovationType, tuple[str, ...]]] = [
    (InnovationType.EDUCATIONAL, ("edukac", "szkol", "nauczan", "uczni", "dydakty", "kompetenc")),
    (InnovationType.SOCIAL, ("spolecz", "integrac", "wykluczen", "senior", "mieszkanc", "wolontar")),
    (InnovationType.PROCESS, ("zarzadzan", "proces", "procedur", "optymaliz", "logisty")),
    (InnovationType.ORGANISATIONAL, ("wspolprac", "partnerst", "sieci wspolpracy", "koordynac", "transgraniczn")),
]
INSTITUTION_KEYWORDS: list[tuple[InstitutionType, tuple[str, ...]]] = [
    (InstitutionType.SCHOOL, ("szkola podstaw", "zespol szkol", "liceum", "technikum", "przedszkol", "szkola branzow")),
    (InstitutionType.UNIVERSITY, ("uniwersytet", "politechnik", "akademi", "uczelni", "wyzsza szkola", "instytut",
                                  "university")),
    (InstitutionType.LOCAL_GOVERNMENT, ("gmina", "powiat", "miasto", "wojewodztwo", "zwiazek gmin", "urzad", "starostw",
                                        "commune", "district", "municipal", "city of")),
    (InstitutionType.PUBLIC_INSTITUTION, ("centrum", "muzeum", "biblioteka", "szpital", "park narodowy", "agencja",
                                          "lasy panstwowe", "straz", "osrodek", "arboretum", "hospital", "station",
                                          "medical care", "centre")),
]

REGIONS = ("Dolnośląskie", "Kujawsko-pomorskie", "Lubelskie", "Lubuskie", "Łódzkie", "Małopolskie",
           "Mazowieckie", "Opolskie", "Podkarpackie", "Podlaskie", "Pomorskie", "Śląskie",
           "Świętokrzyskie", "Warmińsko-mazurskie", "Wielkopolskie", "Zachodniopomorskie")


def region_name(value: str | None) -> str | None:
    return next((name for name in REGIONS if plain(name) == plain(value)), None) if value else None


def application_area(kind: InnovationType, institution: InstitutionType) -> str:
    if kind == InnovationType.EDUCATIONAL:
        return "edukacja"
    if institution == InstitutionType.LOCAL_GOVERNMENT:
        return "administracja"
    if kind == InnovationType.TECHNOLOGICAL or institution in (InstitutionType.UNIVERSITY, InstitutionType.OTHER):
        return "technologia"
    return "administracja"  # organisational, process or social work of a public institution


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").replace("ł", "l").replace("Ł", "L"))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).casefold().split())


def slug(text: str, limit: int = 100) -> str:
    return re.sub(r"[^a-z0-9]+", "-", plain(text)).strip("-")[:limit].strip("-")


def sectors(text: str) -> list[Category]:
    """Sectors ordered by keyword hits; OTHER when nothing matches."""
    haystack = plain(text)
    hits = {sector: sum(haystack.count(word) for word in words) for sector, words in SECTOR_KEYWORDS.items()}
    found = sorted((s for s, n in hits.items() if n), key=lambda s: -hits[s])
    return found or [Category.OTHER]


def first_match(text: str, table):
    haystack = plain(text)
    return next((value for value, words in table if any(word in haystack for word in words)), None)


def innovation_type(text: str, default: InnovationType) -> InnovationType:
    return first_match(text, TYPE_KEYWORDS) or default


COMPANY_MARKERS = ("sp. z o.o", "sp.z o.o", "spolka", "s.a.", "sp. k.", "sp.j.", "sp. j.", "s.c.", "ltd", "gmbh")


def institution_type(name: str) -> InstitutionType:
    if any(marker in plain(name) for marker in COMPANY_MARKERS):
        return InstitutionType.OTHER  # a company, even when named "Centrum" or "Instytut"
    return first_match(name, INSTITUTION_KEYWORDS) or InstitutionType.OTHER


def clip(text: str | None, limit: int = 4000) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rsplit(" ", 1)[0] + "…"


def emit(metas: list[InnovationMeta]) -> None:
    """Validated seed entries on stdout, sorted by id for stable diffs."""
    entries = [{"meta": m.model_dump(mode="json", exclude_none=True)} for m in sorted(metas, key=lambda m: m.id)]
    json.dump(entries, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")


assert sectors("Dron do inspekcji linii energetycznych")[0] in (Category.AVIATION, Category.QUALITY_OF_LIFE)
assert sectors("Nic wspólnego") == [Category.OTHER]
assert sectors("Satellite data for farmers")[0] in (Category.SPACE, Category.QUALITY_OF_LIFE)
assert institution_type("Gmina Sanok") is InstitutionType.LOCAL_GOVERNMENT
assert institution_type("Politechnika Rzeszowska") is InstitutionType.UNIVERSITY
assert institution_type("Centrum Badawczo-Produkcyjne Alcor Sp. z o.o.") is InstitutionType.OTHER
assert slug("PLSK.01.01-IP.01-0001/23") == "plsk-01-01-ip-01-0001-23"
