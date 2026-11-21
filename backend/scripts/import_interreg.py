"""
Import Interreg 2021-2027 projects led by Polish institutions as candidates.

Source: the official list of Interreg 2021-2027 projects (art. 49 CPR) published on
https://interreg.gov.pl/lista-projektow/ as an XLSX file. Partners are institutions.

Usage (from backend/, needs the dev dependencies):
    uv run python scripts/import_interreg.py > data/seed/interreg.json
    uv run python scripts/import_interreg.py --xlsx downloaded.xlsx --url <the page's XLSX link>

Use --region to limit the import to one Polish voivodeship.
"""
import argparse
import datetime as dt
import io
import sys
from urllib.parse import urljoin, urlsplit

import httpx
import lxml.html
import openpyxl

from import_common import USER_AGENT, application_area, clip, emit, innovation_type, institution_type, region_name, sectors, slug
from app.modules.knowledge.schemas import InnovationCard, InnovationMeta
from app.modules.knowledge.taxonomy import InnovationType

INDEX_URL = "https://interreg.gov.pl/lista-projektow/"
HEADER_PREFIX = "Program / Programme"
COLUMNS = {  # Header prefix -> key; the bilingual headers are stable, their order is not assumed.
    "Program": "programme", "Numer projektu": "number", "Tytul projektu": "title", "Opis projektu": "description",
    "Data rozpoczęcia": "start", "Data zakończenia": "end", "Wydatki": "costs", "Stopa dofinansowania": "rate",
    "Nazwa partnera wiodącego/": "lead", "Województwo": "voivodeship", "Nazwa partnera wiodącego i partnerów": "partners",
    "Zakres interwencji": "field",
}


def polish(text) -> str:
    """Bilingual cells are 'Polish / Slovak' or 'Polish/English'; keep the Polish half."""
    return str(text or "").split("/")[0].strip()


def rows(workbook) -> list[dict]:
    sheet = workbook.worksheets[0].iter_rows(values_only=True)
    header = next(r for r in sheet if r and str(r[0] or "").startswith(HEADER_PREFIX))
    keys = [next((k for prefix, k in COLUMNS.items() if str(h or "").startswith(prefix)), None) for h in header]
    return [{k: v for k, v in zip(keys, r) if k} for r in sheet if r and r[1]]


def to_meta(row: dict, url: str, today: dt.date) -> InnovationMeta:
    title, lead = polish(row["title"]), polish(row["lead"])
    text = " ".join(str(row.get(k) or "") for k in ("title", "description", "field"))
    end = row["end"].date() if isinstance(row.get("end"), dt.datetime) else None
    start = row["start"].date() if isinstance(row.get("start"), dt.datetime) else None
    found = sectors(text)
    kind = innovation_type(text, InnovationType.ORGANISATIONAL)
    institution_kind = institution_type(lead)
    evidence = [f"Projekt {row['number']} w programie {polish(row['programme'])}"]
    if start and end:
        evidence.append(f"realizacja {start:%m.%Y}-{end:%m.%Y}")
    if row.get("costs"):
        evidence.append(f"wydatki ogółem {float(row['costs']):,.0f} EUR".replace(",", " "))
    if row.get("rate"):
        evidence.append(f"dofinansowanie UE {row['rate']}%")
    return InnovationMeta(
        id="interreg-" + slug(str(row["number"])),
        title=title[:300],
        categories=found, primary_category=found[0],
        innovation_type=kind, institution_type=institution_kind, institution=lead[:300],
        region=region_name(row.get("voivodeship")), area=application_area(kind, institution_kind),
        source_name="Lista projektów Interreg 2021-2027 (interreg.gov.pl)", source_url=url, imported_at=today,
        checked_at=today,
        card=InnovationCard(
            solution=clip(row.get("description")),
            target_users=clip("Partnerzy projektu: " + str(row.get("partners") or lead)),
            evidence=clip(", ".join(evidence) + "."),
        ),
    )


def latest_workbook(client: httpx.Client) -> str:
    response = client.get(INDEX_URL)
    response.raise_for_status()
    doc = lxml.html.fromstring(response.content)
    for href in doc.xpath("//a/@href"):
        url = urljoin(INDEX_URL, href)
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.netloc == "interreg.gov.pl" and parts.path.lower().endswith(".xlsx"):
            return url
    raise ValueError("The current Interreg workbook link could not be found")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="Override the XLSX link from the official list")
    parser.add_argument("--xlsx", help="Use an already downloaded file instead of fetching --url")
    parser.add_argument("--region", help="Limit to one Polish voivodeship")
    args = parser.parse_args()
    region = region_name(args.region)
    if args.region and not region:
        parser.error("Unknown Polish voivodeship")
    if args.xlsx:
        with open(args.xlsx, "rb") as stream:
            data = stream.read()
        url = args.url or INDEX_URL
    else:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True) as client:
            url = args.url or latest_workbook(client)
            response = client.get(url)
            response.raise_for_status()
            data = response.content
    all_rows = rows(openpyxl.load_workbook(io.BytesIO(data), read_only=True))
    kept = [r for r in all_rows if (name := region_name(r.get("voivodeship"))) and (not region or region == name)]
    if not kept:
        raise ValueError("No projects found for the selected Interreg scope")
    print(f"Interreg: {len(kept)} of {len(all_rows)} projects led from {region or 'Poland'}", file=sys.stderr)
    emit([to_meta(r, url, dt.date.today()) for r in kept])


if __name__ == "__main__":
    main()
