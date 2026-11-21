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
    IDEA = "pomysl"
    PROTOTYPE = "prototyp"
    PILOT = "pilotaz"
    DEPLOYED = "wdrozenie"
    COMMERCIALISED = "komercjalizacja"


MATURITY_LABELS: dict[Maturity, str] = {
    Maturity.IDEA: "Pomysł",
    Maturity.PROTOTYPE: "Prototyp",
    Maturity.PILOT: "Pilotaż / testy",
    Maturity.DEPLOYED: "Wdrożona lokalnie",
    Maturity.COMMERCIALISED: "Skomercjalizowana",
}

assert INNOVATION_TYPE_LABELS.keys() == set(InnovationType)
assert INSTITUTION_TYPE_LABELS.keys() == set(InstitutionType)
assert MATURITY_LABELS.keys() == set(Maturity)
