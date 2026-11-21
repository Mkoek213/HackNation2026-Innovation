"""
Import completed European Funds 2014-2020 projects of Polish public institutions as candidates.

Source: the monthly "Lista projektów realizowanych z Funduszy Europejskich w Polsce w latach 2014-2020"
published by the Ministry of Funds and Regional Policy on gov.pl (XLSX, about 60 MB, no key).
The 2014-2020 list is used because its projects are finished, so each one describes something that was
delivered; no equivalent nationwide 2021-2027 export was found. Kept are projects that:
- have completed funding,
- are run by a school, university, local government or other public institution (name keywords),
- and describe digital, educational or organisational novelty (at least two innovation keywords).
Records are spread round-robin over area and voivodeship so no region dominates.

Usage (from backend/, needs the dev dependencies):
    uv run python scripts/import_fundusze.py > data/seed/fundusze.json
    uv run python scripts/import_fundusze.py --xlsx downloaded.xlsx --limit 500 --region Podkarpackie
"""
import argparse
import datetime as dt
import io
import itertools
import re
import sys
from collections import defaultdict

import httpx
import openpyxl

from import_common import USER_AGENT, clip, emit, innovation_type, institution_type, plain, region_name, sectors, slug
from app.modules.knowledge.schemas import InnovationCard, InnovationMeta
from app.modules.knowledge.taxonomy import InnovationType, InstitutionType

# shortcut: every monthly edition gets a new attachment id; update from the newest edition page on
# https://www.gov.pl/web/fundusze-regiony (search "Lista projektów realizowanych z Funduszy Europejskich 2014-2020").
DEFAULT_URL = "https://www.gov.pl/attachment/b50c1da7-9620-4d86-b35b-b0c723f65f07"  # edition of 30 June 2026
SOURCE_PAGE = ("https://www.gov.pl/web/fundusze-regiony/"
               "lista-projektow-realizowanych-z-funduszy-europejskich-2014-2020---30-czerwca-2026-roku")
COLUMNS = {  # header prefix -> key; order is not assumed
    "Tytuł projektu": "title", "Skrócony opis": "summary", "Numer umowy": "number", "Nazwa beneficjenta": "beneficiary",
    "Program": "programme", "Wartość projektu": "value", "Wartość unijnego": "eu", "Miejsce": "place",
    "Data rozpoczęcia": "start", "Data zakończenia": "end", "Obszar wsparcia": "field", "Finansowanie zakończone": "done",
}
INNOVATION_KEYWORDS = ("innowac", "cyfrow", "e-uslug", "elektroniczn", "platform", "system informat", "aplikac",
                       "nowatorsk", "pilotaz", "e-learning", "laborator", "model ")
EDUCATION_FIELDS = ("049", "050", "051", "115", "116", "117", "118")
ADMINISTRATION_FIELDS = ("078", "079", "080", "081", "119")


def score(row: dict) -> int:
    text = plain(f"{row['title']} {row['summary']}")
    return sum(word in text for word in INNOVATION_KEYWORDS)


def voivodeship(place: str) -> str | None:
    match = re.search(r"WOJ\.:\s*([^,|]+)", place or "")
    return region_name(match.group(1).strip()) if match else None


def area(row: dict, kind: InstitutionType) -> str:
    field = str(row["field"] or "")[:3]
    if field in EDUCATION_FIELDS or kind == InstitutionType.SCHOOL:
        return "edukacja"
    if field in ADMINISTRATION_FIELDS or kind in (InstitutionType.LOCAL_GOVERNMENT, InstitutionType.PUBLIC_INSTITUTION):
        return "administracja"
    return "technologia"


def rows(workbook) -> list[dict]:
    sheet = workbook.worksheets[0].iter_rows(values_only=True)
    header = next(r for r in sheet if r and str(r[0] or "").startswith("Tytuł projektu"))
    keys = [next((k for prefix, k in COLUMNS.items() if str(h or "").startswith(prefix)), None) for h in header]
    return [{k: v for k, v in zip(keys, r) if k} for r in sheet if r and r[0]]


def to_meta(row: dict, kind: InstitutionType, today: dt.date) -> InnovationMeta:
    text = f"{row['title']} {row['summary']} {row['field']}"
    found = sectors(text)
    where = area(row, kind)
    default = {"edukacja": InnovationType.EDUCATIONAL, "administracja": InnovationType.PROCESS}.get(where, InnovationType.TECHNOLOGICAL)
    beneficiary = " ".join(str(row["beneficiary"]).split()).title()
    evidence = [f"Projekt {row['number']} w programie {row['programme']}"]
    if isinstance(row["start"], dt.datetime) and isinstance(row["end"], dt.datetime):
        evidence.append(f"realizacja {row['start']:%m.%Y}-{row['end']:%m.%Y}")
    if row["value"]:
        evidence.append(f"wartość {float(row['value']):,.0f} zł".replace(",", " "))
    if row["eu"]:
        evidence.append(f"dofinansowanie UE {float(row['eu']):,.0f} zł".replace(",", " "))
    evidence.append("finansowanie zakończone")
    return InnovationMeta(
        id="fe-" + slug(str(row["number"])),
        title=clip(str(row["title"]), 300),
        categories=found, primary_category=found[0],
        innovation_type=innovation_type(text, default), institution_type=kind, institution=clip(beneficiary, 300),
        region=voivodeship(row["place"]), area=where,
        source_name="Lista projektów Funduszy Europejskich 2014-2020 (Ministerstwo Funduszy i Polityki Regionalnej)",
        source_url=SOURCE_PAGE, imported_at=today, checked_at=today,
        card=InnovationCard(
            solution=clip(str(row["summary"] or "")),
            target_users=clip(f"Beneficjent: {beneficiary}. Miejsce realizacji: {row['place']}."),
            evidence=clip(", ".join(evidence) + "."),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=DEFAULT_URL, help="XLSX attachment of the newest monthly edition")
    parser.add_argument("--xlsx", help="Use an already downloaded file instead of fetching --url")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--region", help="Limit to one Polish voivodeship")
    args = parser.parse_args()
    region = region_name(args.region)
    if args.region and not region:
        parser.error("Unknown Polish voivodeship")
    if args.xlsx:
        data = open(args.xlsx, "rb").read()
    else:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=600, follow_redirects=True) as client:
            response = client.get(args.url)
            response.raise_for_status()
            data = response.content
    all_rows = rows(openpyxl.load_workbook(io.BytesIO(data), read_only=True))
    today = dt.date.today()
    groups: dict[tuple, list[tuple[int, InnovationMeta]]] = defaultdict(list)
    for row in all_rows:
        kind = institution_type(str(row["beneficiary"]))
        if row.get("done") != "Tak" or kind == InstitutionType.OTHER or not row.get("summary") or (points := score(row)) < 2:
            continue
        meta = to_meta(row, kind, today)
        if not region or meta.region == region:
            groups[(meta.area, meta.region)].append((points, meta))
    for items in groups.values():
        items.sort(key=lambda item: (-item[0], item[1].id))
    # Round-robin across (area, voivodeship) groups, strongest innovation signal first.
    ordered = [item[1] for layer in itertools.zip_longest(*groups.values()) for item in layer if item]
    kept = list({m.id: m for m in ordered}.values())[:args.limit]
    if not kept:
        raise ValueError("No European Funds projects found for the selected scope")
    print(f"Fundusze Europejskie: {len(kept)} of {sum(map(len, groups.values()))} eligible of {len(all_rows)} projects",
          file=sys.stderr)
    emit(kept)


assert voivodeship("WOJ.: PODKARPACKIE, POW.: Rzeszów | WOJ.: MAŁOPOLSKIE") == "Podkarpackie"
assert voivodeship("Cały Kraj") is None
assert score({"title": "Platforma e-usług", "summary": "Cyfrowe usługi"}) >= 2

if __name__ == "__main__":
    main()
