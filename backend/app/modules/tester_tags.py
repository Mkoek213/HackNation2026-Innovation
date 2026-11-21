"""Fixed tag lists a pilot partner picks explicitly: who they are and which sectors they can pilot.

In Radar innowacji the "tester" pool holds pilot partners: institutions, companies and experts
ready to pilot, deploy, develop or fund an innovation. Interests reuse the knowledge sectors, so
partner interests match innovation sectors directly. Labels are user-facing (Polish).
"""
from enum import StrEnum

from app.modules.knowledge import CATEGORY_LABELS, Category


class TesterRole(StrEnum):
    SCHOOL = "szkola"
    UNIVERSITY = "uczelnia"
    LOCAL_GOVERNMENT = "jst"
    PUBLIC_INSTITUTION = "instytucja-publiczna"
    COMPANY = "przedsiebiorstwo"
    STARTUP = "startup"
    NGO = "organizacja-pozarzadowa"
    INVESTOR = "inwestor"
    EXPERT = "ekspert"


ROLE_LABELS: dict[TesterRole, str] = {
    TesterRole.SCHOOL: "Szkoła",
    TesterRole.UNIVERSITY: "Uczelnia lub instytut badawczy",
    TesterRole.LOCAL_GOVERNMENT: "Jednostka samorządu terytorialnego",
    TesterRole.PUBLIC_INSTITUTION: "Inna instytucja publiczna",
    TesterRole.COMPANY: "Przedsiębiorstwo",
    TesterRole.STARTUP: "Startup",
    TesterRole.NGO: "Organizacja pozarządowa",
    TesterRole.INVESTOR: "Inwestor lub fundusz",
    TesterRole.EXPERT: "Ekspert lub mentor",
}

INTEREST_LABELS: dict[Category, str] = CATEGORY_LABELS

assert ROLE_LABELS.keys() == set(TesterRole)
