"""Single source of truth for innovation classification axes.

`Category` is the sector axis (the PCI smart-specialisation sectors). It types the API
schemas, the Qdrant payload and the GLiDE classification, so an unknown sector cannot
enter the system. Innovation type, source institution type and maturity are descriptive
axes from the PCI "Radar innowacji" brief; they are set by importers or the admin.
"""
from enum import StrEnum


class Category(StrEnum):
    AUTOMOTIVE = "motoryzacja"
    AVIATION = "lotnictwo"
    SPACE = "kosmos"
    ICT = "ict"
    QUALITY_OF_LIFE = "jakosc-zycia"
    OTHER = "inne"


# User-facing labels (product copy is Polish).
CATEGORY_LABELS: dict[Category, str] = {
    Category.AUTOMOTIVE: "Motoryzacja i mobilność",
    Category.AVIATION: "Lotnictwo",
    Category.SPACE: "Sektor kosmiczny",
    Category.ICT: "ICT i cyfryzacja",
    Category.QUALITY_OF_LIFE: "Jakość życia",
    Category.OTHER: "Inne obszary",
}

# Decision-model criteria. Written in English because GLiDE's documented accuracy is
# highest in English; the evaluated state (innovation text) stays Polish.
CATEGORY_CRITERIA: dict[Category, str] = {
    Category.AUTOMOTIVE: "Automotive and mobility: vehicles, drives, batteries, transport systems, road safety, logistics",
    Category.AVIATION: "Aviation: aircraft, drones, aerospace materials and manufacturing, avionics, airports",
    Category.SPACE: "Space sector: satellites, satellite data, space technologies, Earth observation",
    Category.ICT: "ICT and digitalisation: software, AI, data, electronics, networks, e-services, cybersecurity",
    Category.QUALITY_OF_LIFE: "Quality of life: health, medicine, food, environment, energy, education, social inclusion, public services",
    Category.OTHER: "Other areas not covered by automotive, aviation, space, ICT or quality of life",
}

assert CATEGORY_LABELS.keys() == CATEGORY_CRITERIA.keys() == set(Category)


class InnovationType(StrEnum):
    TECHNOLOGICAL = "technologiczna"
    ORGANISATIONAL = "organizacyjna"
    EDUCATIONAL = "edukacyjna"
    SOCIAL = "spoleczna"
    PROCESS = "procesowa"


INNOVATION_TYPE_LABELS: dict[InnovationType, str] = {
    InnovationType.TECHNOLOGICAL: "Technologiczna",
    InnovationType.ORGANISATIONAL: "Organizacyjna",
    InnovationType.EDUCATIONAL: "Edukacyjna",
    InnovationType.SOCIAL: "Społeczna",
    InnovationType.PROCESS: "Procesowa",
}


class InstitutionType(StrEnum):
    SCHOOL = "szkola"
    UNIVERSITY = "uczelnia"
    LOCAL_GOVERNMENT = "jst"
    PUBLIC_INSTITUTION = "instytucja-publiczna"
    OTHER = "inna"


INSTITUTION_TYPE_LABELS: dict[InstitutionType, str] = {
    InstitutionType.SCHOOL: "Szkoła",
    InstitutionType.UNIVERSITY: "Uczelnia",
    InstitutionType.LOCAL_GOVERNMENT: "Jednostka samorządu terytorialnego",
    InstitutionType.PUBLIC_INSTITUTION: "Inna instytucja publiczna",
    InstitutionType.OTHER: "Inny podmiot",
}


class Maturity(StrEnum):
    """Deployment level from the PCI FAQ (section 5)."""
    CONCEPT = "koncepcja"
    PROTOTYPE = "prototyp"
    TESTING = "testy"
    PILOT = "pilotaz"
    IN_USE = "stosowane"

    @classmethod
    def _missing_(cls, value):
        # Cards stored before the FAQ alignment; commercialisation is now a path, not a stage.
        return {"pomysl": cls.CONCEPT, "wdrozenie": cls.IN_USE, "komercjalizacja": cls.IN_USE}.get(value)


MATURITY_LABELS: dict[Maturity, str] = {
    Maturity.CONCEPT: "Koncepcja",
    Maturity.PROTOTYPE: "Prototyp",
    Maturity.TESTING: "Testy",
    Maturity.PILOT: "Wdrożenie pilotażowe",
    Maturity.IN_USE: "Stosowane w praktyce",
}



class Audience(StrEnum):
    """FAQ target groups that can deploy, transfer or fund a solution."""
    LOCAL_GOVERNMENT = "jst"
    PUBLIC_INSTITUTION = "instytucja-publiczna"
    UNIVERSITY = "uczelnia"
    SCHOOL = "szkola"
    COMPANY = "przedsiebiorstwo"
    INVESTOR = "inwestor"


AUDIENCE_LABELS: dict[Audience, str] = {
    Audience.LOCAL_GOVERNMENT: "Samorząd (JST)",
    Audience.PUBLIC_INSTITUTION: "Instytucja publiczna",
    Audience.UNIVERSITY: "Uczelnia lub jednostka naukowa",
    Audience.SCHOOL: "Szkoła lub placówka edukacyjna",
    Audience.COMPANY: "Przedsiębiorstwo lub startup",
    Audience.INVESTOR: "Inwestor",
}


class DevelopmentPath(StrEnum):
    DEPLOYMENT = "wdrozenie"
    TRANSFER = "transfer"
    DEVELOPMENT = "rozwoj"
    COMMERCIALISATION = "komercjalizacja"


PATH_LABELS: dict[DevelopmentPath, str] = {
    DevelopmentPath.DEPLOYMENT: "Wdrożenie w kolejnej instytucji",
    DevelopmentPath.TRANSFER: "Transfer do innej organizacji lub branży",
    DevelopmentPath.DEVELOPMENT: "Dalszy rozwój i testy",
    DevelopmentPath.COMMERCIALISATION: "Komercjalizacja",
}

# The five FAQ criteria (section 5): key -> (label, what a high score means). Scores are 1-5.
# Bump CRITERIA_VERSION whenever these texts or the scoring rules change; cards are then reassessed.
CRITERIA_VERSION = "kryteria-2026-11"
ASSESSMENT_CRITERIA: dict[str, tuple[str, str]] = {
    "implementation": ("Poziom wdrożenia",
                       "Etap od koncepcji do stosowania w praktyce. Wysoka ocena oznacza rzeczywiste użycie poza projektem."),
    "trl": ("Dojrzałość technologiczna (TRL 1-9)",
            "Tylko dla rozwiązań technologicznych. TRL 9 to system sprawdzony w środowisku operacyjnym."),
    "novelty": ("Innowacyjność",
                "Stopień nowości lub ulepszenia względem rozwiązań już stosowanych w Polsce (Oslo Manual 2018)."),
    "transfer": ("Potencjał zastosowania",
                 "Możliwość użycia w innych instytucjach, organizacjach lub branżach bez dużych zmian."),
    "credibility": ("Wiarygodność",
                    "Liczona regułami: oficjalne źródło, potwierdzenie wdrożenia, dokumenty i opis dowodów."),
}

assert INNOVATION_TYPE_LABELS.keys() == set(InnovationType)
assert INSTITUTION_TYPE_LABELS.keys() == set(InstitutionType)
assert MATURITY_LABELS.keys() == set(Maturity)
assert Maturity("wdrozenie") is Maturity.IN_USE
assert AUDIENCE_LABELS.keys() == set(Audience) and PATH_LABELS.keys() == set(DevelopmentPath)
