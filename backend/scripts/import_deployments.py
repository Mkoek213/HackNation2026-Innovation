"""
Check public deployment reports selected for the verified catalog.

Each report names exact phrases (anchors) that must appear on the publisher's page; only then is the card
confirmed with documented real-world use. Otherwise it stays a candidate for review.

Usage (from backend/):
    uv run python scripts/import_deployments.py > data/seed/deployments.json
"""
import datetime as dt
import sys
from dataclasses import dataclass

import httpx
import lxml.html

from import_common import USER_AGENT, emit, plain
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
    maturity: Maturity = Maturity.IN_USE


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
    Report(
        id="gov-e-doreczenia", title="e-Doręczenia · elektroniczna korespondencja z urzędami",
        url="https://www.gov.pl/web/cyfryzacja/100-mln-przesylek-w-e-doreczeniach-cyfrowa-korespondencja-z-urzedami-stala-sie-standardem",
        publisher="Ministerstwo Cyfryzacji", institution="Ministerstwo Cyfryzacji · urzędy w całej Polsce",
        region=None, area="administracja", kind=InnovationType.PROCESS,
        institution_kind=InstitutionType.PUBLIC_INSTITUTION, sector=Category.ICT,
        anchors=("przekroczyła już 100 mln", "4,6 mln adresów"),
        solution="Elektroniczny odpowiednik listu poleconego za potwierdzeniem odbioru w korespondencji z urzędami.",
        implementation="Według Ministerstwa Cyfryzacji (sierpień 2026) wysłano ponad 100 mln przesyłek, a w Bazie Adresów Elektronicznych jest 4,6 mln adresów.",
        novelty="Urząd doręcza pismo z mocą prawną listu poleconego bez druku i bez wizyty na poczcie.",
        transfer="Usługa jest powszechna dla podmiotów publicznych. Korzyść w danej instytucji zależy od integracji z jej systemem obiegu dokumentów.",
        next_step="Kancelaria urzędu może zmierzyć udział korespondencji wysyłanej elektronicznie i koszt wysyłki papierowej przed i po pełnym przejściu na e-Doręczenia.",
    ),
    Report(
        id="gov-laboratoria-przyszlosci", title="Laboratoria Przyszłości · wyposażenie szkół w sprzęt do nauki przez działanie",
        url="https://www.gov.pl/web/nauka/niemal-miliard-zlotych-w-ramach-laboratoriow-przyszlosci-juz-w-szkolach-w-calej-polsce",
        publisher="Ministerstwo Edukacji i Nauki", institution="Szkoły podstawowe w całej Polsce",
        region=None, area="edukacja", kind=InnovationType.EDUCATIONAL,
        institution_kind=InstitutionType.SCHOOL, sector=Category.QUALITY_OF_LIFE,
        anchors=("zgłosiło się ponad 99%", "niemal miliard złotych trafił już do szkół"),
        solution="Program finansowania drukarek 3D, mikrokontrolerów, robotów edukacyjnych i innego sprzętu do rozwijania kompetencji przyszłości w szkołach podstawowych.",
        implementation="Do pierwszej odsłony zgłosiło się ponad 99% z niemal 12 tys. uprawnionych szkół, a niemal miliard złotych trafił już do szkół w całym kraju.",
        novelty="Szkoła sama wybiera wyposażenie z katalogu niemal 200 rodzajów sprzętu i wykorzystuje je na zajęciach projektowych.",
        transfer="Sprzęt jest już w większości szkół. Efekt zależy od przygotowania nauczycieli i scenariuszy zajęć, a nie od samego zakupu.",
        next_step="Dyrekcja może zaplanować jeden projekt uczniowski z użyciem sprzętu na semestr i zmierzyć liczbę godzin zajęć z jego wykorzystaniem.",
    ),
    Report(
        id="gov-ose", title="Ogólnopolska Sieć Edukacyjna (OSE) · szybki i bezpieczny internet w szkołach",
        url="https://www.gov.pl/web/cyfryzacja/ose-szybki-internet-w-szkolach-sprzet-dla-uczniow-i-nauczycieli",
        publisher="Ministerstwo Cyfryzacji", institution="NASK-PIB · szkoły w całej Polsce",
        region=None, area="edukacja", kind=InnovationType.TECHNOLOGICAL,
        institution_kind=InstitutionType.PUBLIC_INSTITUTION, sector=Category.ICT,
        anchors=("tysiąca szkół podpisało umowy z ose", "tysiąca placówek jest już do ose podłączona"),
        solution="Publiczna sieć telekomunikacyjna, która daje szkołom bezpłatny, szybki i filtrowany dostęp do internetu.",
        implementation="Ministerstwo Cyfryzacji podało, że 18,5 tys. szkół podpisało umowy z OSE, a 14,6 tys. placówek było już podłączonych.",
        novelty="Jeden operator publiczny dostarcza szkołom łącze, ochronę przed szkodliwymi treściami i zabezpieczenia sieci.",
        transfer="Sieć obejmuje większość szkół. Szkoła spoza sieci sprawdza dostępność przyłącza i wewnętrzną infrastrukturę Wi-Fi.",
        next_step="Organ prowadzący może sprawdzić, które szkoły nie korzystają z OSE, i zmierzyć dostępną przepustowość na ucznia przed i po podłączeniu.",
    ),
    Report(
        id="podkarpackie-pseap", title="PSeAP · Podkarpacki System e-Administracji Publicznej",
        url="https://samorzad.gov.pl/web/powiat-jasielski/pseap---podkarpacki-system-e-administracji-publicznej.",
        publisher="Powiat Jasielski (samorzad.gov.pl)", institution="Samorząd Województwa Podkarpackiego i partnerzy JST · Powiat Jasielski",
        region="Podkarpackie", area="administracja", kind=InnovationType.PROCESS,
        institution_kind=InstitutionType.LOCAL_GOVERNMENT, sector=Category.ICT,
        anchors=("wdrożenie systemu e-usług internetowych (seui)", "systemu elektronicznego obiegu dokumentów (seod)"),
        solution="Regionalne środowisko e-administracji dla urzędów samorządowych: wspólny system e-usług internetowych i elektroniczny obieg dokumentów.",
        implementation="Powiat Jasielski opisuje wdrożenie Systemu e-Usług Internetowych (SeUI) i Systemu Elektronicznego Obiegu Dokumentów (SEOD) w ramach PSeAP.",
        novelty="Urzędy jednego województwa korzystają ze wspólnej platformy zamiast budować e-usługi osobno.",
        transfer="Model wspólnej regionalnej platformy można powtórzyć w innym województwie. Wymaga to umów utrzymaniowych i integracji z ePUAP oraz e-Doręczeniami.",
        next_step="Sekretarz gminy może porównać, które e-usługi z PSeAP są aktywne, i zmierzyć udział spraw wszczętych elektronicznie.",
    ),
    Report(
        id="rzeszow-ismp", title="Inteligentny System Monitoringu Przystanków w Rzeszowie",
        url="https://www.assecods.pl/en/case-studies/intelligent-bus-stop-monitoring-system",
        publisher="Asseco Data Systems (opis wdrożenia wykonawcy)", institution="Zarząd Transportu Miejskiego w Rzeszowie",
        region="Podkarpackie", area="technologia", kind=InnovationType.TECHNOLOGICAL,
        institution_kind=InstitutionType.LOCAL_GOVERNMENT, sector=Category.AUTOMOTIVE,
        anchors=("installed at 47 bus stops across rzeszów", "electronic passenger information system"),
        solution="Monitoring wizyjny przystanków komunikacji miejskiej połączony z elektronicznym systemem informacji pasażerskiej.",
        implementation="Według opisu wykonawcy system zainstalowano na 47 przystankach w Rzeszowie i zintegrowano z systemem informacji pasażerskiej działającym od 2015 r.",
        novelty="Obraz z przystanków trafia do tego samego systemu, który zarządza informacją dla pasażerów.",
        transfer="Rozwiązanie pasuje do miast z istniejącym systemem informacji pasażerskiej. Opis pochodzi od wykonawcy, więc efekty wymagają potwierdzenia przez ZTM.",
        next_step="Zarząd transportu może poprosić ZTM Rzeszów o dane o incydentach i aktach wandalizmu przed i po wdrożeniu, a potem zaplanować pilotaż na kilku przystankach.",
    ),
    Report(
        id="podkarpackie-rap-steam", title="RaP STEAM · robotyka i programowanie w podkarpackich szkołach podstawowych",
        url="https://samorzad.gov.pl/web/gmina-grodzisko-dolne/gmina-grodzisko-dolne-partnerem-programu-rap-steam",
        publisher="Gmina Grodzisko Dolne (samorzad.gov.pl)", institution="Samorząd Województwa Podkarpackiego · szkoły podstawowe regionu",
        region="Podkarpackie", area="edukacja", kind=InnovationType.EDUCATIONAL,
        institution_kind=InstitutionType.LOCAL_GOVERNMENT, sector=Category.ICT,
        anchors=("zgłosiło się aż 771 publicznych i niepublicznych szkół", "testowane różne rozwiązania programu w ramach pilotażu"),
        solution="Regionalny program nauczania robotyki z elementami programowania w szkołach podstawowych województwa podkarpackiego.",
        implementation="Do projektu zgłosiło się 771 szkół podstawowych. Rozwiązania są testowane pilotażowo w Zespole Szkół w Grodzisku Górnym.",
        novelty="Samorząd województwa prowadzi jeden program robotyki dla setek szkół i najpierw testuje go w szkole z doświadczeniem w robotyce.",
        transfer="Model regionalnego programu można przenieść do innego województwa. Warunkiem jest finansowanie EFS+ i przygotowanie nauczycieli.",
        next_step="Inny samorząd może poprosić o wyniki pilotażu w Grodzisku Górnym i zmierzyć liczbę uczniów uczestniczących w zajęciach robotyki.",
        maturity=Maturity.PILOT,
    ),
    Report(
        id="gov-e-recepta", title="e-Recepta · elektroniczna recepta w każdej aptece",
        url="https://pacjent.gov.pl/e-recepta",
        publisher="Centrum e-Zdrowia (pacjent.gov.pl)", institution="Centrum e-Zdrowia · apteki i placówki medyczne w całej Polsce",
        region=None, area="technologia", kind=InnovationType.TECHNOLOGICAL,
        institution_kind=InstitutionType.PUBLIC_INSTITUTION, sector=Category.QUALITY_OF_LIFE,
        anchors=("zastąpił tradycyjną, papierową receptę", "zrealizujesz ją w każdej aptece w polsce"),
        solution="Elektroniczna recepta realizowana na podstawie czterocyfrowego kodu, zapisana na Internetowym Koncie Pacjenta.",
        implementation="Centrum e-Zdrowia opisuje e-receptę jako dokument, który zastąpił papierową receptę i jest realizowany w każdej aptece w Polsce.",
        novelty="Pacjent może kupić każdy lek z recepty w innej aptece, a recepta jest zawsze czytelna i zapisana na koncie.",
        transfer="Usługa jest powszechna. Wnioski dla innych instytucji dotyczą modelu centralnego rejestru i kodu dostępu wysyłanego SMS-em.",
        next_step="Instytucja projektująca podobną e-usługę może przeanalizować model kodu dostępu i zmierzyć odsetek spraw załatwionych bez wizyty.",
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
                    next_step=report.next_step,
                    # Credibility is computed by the assessment rules for every card alike.
                ) if confirmed else InnovationAssessment()
                cards.append(InnovationMeta(
                    id=report.id, title=report.title, categories=[report.sector], primary_category=report.sector,
                    innovation_type=report.kind, institution_type=report.institution_kind, institution=report.institution,
                    region=report.region, area=report.area,
                    verification="potwierdzona" if confirmed else "kandydat",
                    maturity=report.maturity if confirmed else None, assessment=assessment,
                    source_name=report.publisher, source_url=report.url, imported_at=today, checked_at=today,
                    card=InnovationCard(solution=report.solution, evidence=report.implementation if confirmed else ""),
                ))
            except (httpx.HTTPError, ValueError, lxml.etree.LxmlError) as exc:
                failures += 1
                print(f"{report.id}: {exc}", file=sys.stderr)
    return cards, failures


if __name__ == "__main__":
    cards, failures = records()
    emit(cards)
    print(f"Deployments: {len(cards)} checked, {failures} failed", file=sys.stderr)
    raise SystemExit(int(failures > 0))
