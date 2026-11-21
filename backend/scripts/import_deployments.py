"""Check public deployment reports selected for the verified catalog."""
import datetime as dt
import sys
from dataclasses import dataclass

import httpx
import lxml.html

from import_common import USER_AGENT, plain
from app.modules.knowledge.schemas import AssessmentNote, InnovationArea, InnovationAssessment, InnovationCard, InnovationMeta
from app.modules.knowledge.taxonomy import Category, InnovationType, InstitutionType, Maturity


@dataclass(frozen=True)
class Report:
    id: str
    title: str
    url: str
    publisher: str
    institution: str
    region: str | None
    area: InnovationArea
    kind: InnovationType
    institution_kind: InstitutionType
    sector: Category
    anchors: tuple[str, ...]
    solution: str
    implementation: str
    novelty: str
    transfer: str
    next_step: str


REPORTS = (
    Report(
        id="gov-eplatnosci", title="ePłatności dla samorządów",
        url="https://www.gov.pl/web/cyfryzacja/ponad-milion-platnosci-bez-kolejek-cyfrowe-oplaty-urzedowe-staja-sie-standardem",
        publisher="Ministerstwo Cyfryzacji", institution="Centralny Ośrodek Informatyki · wdrożenie w Bydgoszczy",
        region="Kujawsko-pomorskie", area="administracja", kind=InnovationType.PROCESS,
        institution_kind=InstitutionType.PUBLIC_INSTITUTION, sector=Category.ICT,
        anchors=("bydgoszczy zrealizowano pierwszą transakcję", "1,1 mln transakcji"),
        solution="Płatności online dla mieszkańców. Podatki lokalne i inne należności urzędowe można opłacić cyfrowo w mObywatelu.",
        implementation="Bydgoszcz obsłużyła pierwszą transakcję. Według raportu z maja 2026 r. w Polsce wykonano ponad 1,1 mln transakcji.",
        novelty="Mieszkaniec reguluje należność urzędową z poziomu aplikacji, bez ręcznego przepisywania danych do przelewu.",
        transfer="Usługa działa w dużych miastach i mniejszych gminach. Zakres należności i połączenie z systemem księgowym zależą od urzędu.",
        next_step="Wydział finansowy gminy może uzgodnić z COI obsługę jednej należności po sprawdzeniu integracji. W pilotażu zmierzyć odsetek wpłat online.",
    ),
    Report(
        id="gov-ezd-rp", title="EZD RP · elektroniczny obieg dokumentów",
        url="https://www.gov.pl/web/ezd-rp/770-zrealizowanych-wdrozen-produkcyjnych-ezd-rp",
        publisher="Portal EZD RP", institution="NASK-PIB · wdrożenie w Białymstoku",
        region="Podlaskie", area="technologia", kind=InnovationType.TECHNOLOGICAL,
        institution_kind=InstitutionType.PUBLIC_INSTITUTION, sector=Category.ICT,
        anchors=("uruchomiono produkcyjnie ezd rp", "urzędzie marszałkowskim województwa podlaskiego"),
        solution="System do elektronicznego zarządzania dokumentacją i obiegu spraw między pracownikami urzędu.",
        implementation="Urząd Marszałkowski Województwa Podlaskiego w Białymstoku uruchomił EZD RP produkcyjnie 2 stycznia 2024 r.",
        novelty="System pozwala rejestrować i przekazywać dokumenty w elektronicznym obiegu spraw urzędu.",
        transfer="Źródło opisuje wdrożenia w wielu instytucjach. W nowym urzędzie trzeba sprawdzić integracje, migrację i organizację pracy.",
        next_step="Sekretarz urzędu może ustalić z zespołem EZD RP warunki wdrożenia w jednym wydziale i zmierzyć czas od rejestracji pisma do jego przekazania.",
    ),
    Report(
        id="lekcja-enter", title="Lekcja:Enter · cyfrowe metody nauczania",
        url="https://lekcjaenter.pl/aktualnosci/zapraszamy-do-obejrzenia-filmu-podsumowujacego-nasz-projekt",
        publisher="Lekcja:Enter · organizatorzy programu", institution="Konsorcjum Lekcja:Enter i uczestniczące szkoły",
        region=None, area="edukacja", kind=InnovationType.EDUCATIONAL,
        institution_kind=InstitutionType.SCHOOL, sector=Category.QUALITY_OF_LIFE,
        anchors=("82 tysiące nauczycielek i nauczycieli", "10 000 szkół"),
        solution="Model doskonalenia nauczycieli w tworzeniu i prowadzeniu lekcji z wykorzystaniem narzędzi cyfrowych.",
        implementation="Organizatorzy podają, że z wdrożonego programu szkoleń skorzystało ponad 82 tys. nauczycieli z ponad 10 tys. szkół.",
        novelty="Model łączy szkolenie metodyczne z przygotowywaniem scenariuszy zajęć przez nauczycieli.",
        transfer="Wynik pokazuje zasięg szkoleń. Dostępność materiałów i efekty zastosowania metody w danej szkole wymagają sprawdzenia.",
        next_step="Dyrekcja może wypróbować jeden opublikowany scenariusz po sprawdzeniu dostępności materiałów i zebrać ocenę nauczycieli oraz uczniów.",
    ),
)


def records() -> tuple[list[InnovationMeta], int]:
    cards = []
    failures = 0
    today = dt.date.today()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as client:
        for report in REPORTS:
            try:
                response = client.get(report.url)
                response.raise_for_status()
                page = lxml.html.fromstring(response.text)
                text = plain(" ".join(page.xpath("//body//text()[not(ancestor::script) and not(ancestor::style)]")))
                if len(text) < 500:
                    raise ValueError("Source response lacks readable text")
                confirmed = all(plain(anchor) in text for anchor in report.anchors)
                if not confirmed:
                    print(f"{report.id}: expected evidence missing; review candidate", file=sys.stderr)
                assessment = InnovationAssessment(
                    implementation=AssessmentNote(basis="potwierdzone", rationale=report.implementation, source_url=report.url),
                    novelty=AssessmentNote(basis="szacunek", rationale=report.novelty, source_url=report.url),
                    transfer=AssessmentNote(basis="szacunek", rationale=report.transfer, source_url=report.url),
                    credibility=AssessmentNote(basis="potwierdzone",
                        rationale="Publiczny opis administratora usługi lub realizatora programu. Zakres dowodu wynika z publikacji.",
                        source_url=report.url),
                    next_step=report.next_step,
                ) if confirmed else InnovationAssessment()
                cards.append(InnovationMeta(
                    id=report.id, title=report.title, categories=[report.sector], primary_category=report.sector,
                    innovation_type=report.kind, institution_type=report.institution_kind, institution=report.institution,
                    region=report.region, area=report.area,
                    verification="potwierdzona" if confirmed else "kandydat",
                    maturity=Maturity.IN_USE if confirmed else None, assessment=assessment,
                    source_name=report.publisher, source_url=report.url, imported_at=today, checked_at=today,
                    card=InnovationCard(solution=report.solution, evidence=report.implementation if confirmed else ""),
                ))
            except (httpx.HTTPError, ValueError, lxml.etree.LxmlError) as exc:
                failures += 1
                print(f"{report.id}: {exc}", file=sys.stderr)
    return cards, failures
