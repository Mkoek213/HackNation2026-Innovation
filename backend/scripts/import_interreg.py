"""
Import Interreg 2021-2027 projects led by Podkarpackie institutions as innovation cards.

Source: the official list of Interreg 2021-2027 projects (art. 49 CPR) published on
https://interreg.gov.pl/lista-projektow/ as an XLSX file. Only projects whose lead partner is
in województwo podkarpackie are kept. Partners are institutions; no personal data is read.

Usage (from backend/, needs the dev dependencies):
    uv run python scripts/import_interreg.py > data/seed/interreg.json
    uv run python scripts/import_interreg.py --xlsx downloaded.xlsx --url <the page's XLSX link>

The XLSX file name changes with every update; pass the current link from the list page.
"""
import argparse
import datetime as dt
import io
import sys

import httpx
import openpyxl

from import_common import USER_AGENT, clip, emit, innovation_type, institution_type, sectors, slug
from app.modules.knowledge.schemas import InnovationCard, InnovationMeta
from app.modules.knowledge.taxonomy import InnovationType, Maturity

DEFAULT_URL = "https://interreg.gov.pl/wp-content/uploads/2026/11/Wykaz_projektow_Interreg_2021-2027_art_49_CPR_20261116.xlsx"
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
        innovation_type=innovation_type(text, InnovationType.ORGANISATIONAL),
        institution_type=institution_type(lead), institution=lead[:300],
        maturity=Maturity.DEPLOYED if end and end < today else Maturity.PILOT,
        source_name="Lista projektów Interreg 2021-2027 (interreg.gov.pl)", source_url=url, imported_at=today,
        card=InnovationCard(
            solution=clip(row.get("description")),
            target_users=clip("Partnerzy projektu: " + str(row.get("partners") or lead)),
            evidence=clip(", ".join(evidence) + "."),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=DEFAULT_URL, help="XLSX link from https://interreg.gov.pl/lista-projektow/")
    parser.add_argument("--xlsx", help="Use an already downloaded file instead of fetching --url")
    args = parser.parse_args()
    if args.xlsx:
        data = open(args.xlsx, "rb").read()
    else:
        response = httpx.get(args.url, headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True)
        response.raise_for_status()
        data = response.content
    all_rows = rows(openpyxl.load_workbook(io.BytesIO(data), read_only=True))
    kept = [r for r in all_rows if "PODKARPA" in str(r.get("voivodeship") or "").upper()]
    print(f"Interreg: {len(kept)} of {len(all_rows)} projects led from Podkarpackie", file=sys.stderr)
    emit([to_meta(r, args.url, dt.date.today()) for r in kept])


if __name__ == "__main__":
    main()
