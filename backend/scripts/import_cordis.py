"""
Import Horizon Europe projects with Polish coordinators or participants from CORDIS as candidates.

Source: the official CORDIS open data export of the European Commission
(https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip, CC BY 4.0), no key required.
Projects are joined with their Polish organisations; the coordinator is preferred as the institution.
Fellowships (MSCA), ERC frontier research, co-funding and terminated projects are skipped because they
do not describe a solution that can be deployed. Close-to-market schemes (innovation actions, EIC,
pre-commercial procurement) and Polish coordinators come first. Texts stay in English as published.

Usage (from backend/):
    uv run python scripts/import_cordis.py > data/seed/cordis.json
    uv run python scripts/import_cordis.py --zip downloaded.zip --limit 400 --region Podkarpackie
"""
import argparse
import csv
import datetime as dt
import io
import sys
import zipfile
from collections import defaultdict

import httpx

from import_common import USER_AGENT, clip, emit, plain, region_name, sectors
from app.modules.knowledge.schemas import InnovationCard, InnovationMeta
from app.modules.knowledge.taxonomy import InnovationType, InstitutionType

URL = "https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip"
# NUTS 2021 level 2 -> voivodeship (PL91 and PL92 are both Mazowieckie).
NUTS2 = {
    "PL21": "Małopolskie", "PL22": "Śląskie", "PL41": "Wielkopolskie", "PL42": "Zachodniopomorskie",
    "PL43": "Lubuskie", "PL51": "Dolnośląskie", "PL52": "Opolskie", "PL61": "Kujawsko-pomorskie",
    "PL62": "Warmińsko-mazurskie", "PL63": "Pomorskie", "PL71": "Łódzkie", "PL72": "Świętokrzyskie",
    "PL81": "Lubelskie", "PL82": "Podkarpackie", "PL84": "Podlaskie", "PL91": "Mazowieckie", "PL92": "Mazowieckie",
}
# Funding scheme family -> priority (lower first); missing families are skipped.
SCHEMES = {"IA": 0, "EIC": 0, "PCP": 0, "PPI": 0, "JU": 1, "RIA": 2, "CSA": 3}
ACTIVITY = {  # CORDIS activityType -> institution type
    "HES": InstitutionType.UNIVERSITY, "REC": InstitutionType.PUBLIC_INSTITUTION,
    "PUB": InstitutionType.PUBLIC_INSTITUTION, "PRC": InstitutionType.OTHER, "OTH": InstitutionType.OTHER,
}
LOCAL_GOVERNMENT = ("gmina", "miasto", "powiat", "wojewodztwo", "urzad", "municipality", "city of")


def scheme(funding_scheme: str) -> str:
    parts = funding_scheme.split("-")
    return parts[1] if len(parts) > 1 else funding_scheme


def institution_kind(org: dict) -> InstitutionType:
    if org["activityType"] == "PUB" and any(word in plain(org["name"]) for word in LOCAL_GOVERNMENT):
        return InstitutionType.LOCAL_GOVERNMENT
    return ACTIVITY.get(org["activityType"], InstitutionType.OTHER)


def read(archive: zipfile.ZipFile, name: str):
    csv.field_size_limit(sys.maxsize)
    rows = csv.DictReader(io.TextIOWrapper(archive.open(name), encoding="utf-8"), delimiter=";")
    # About 1% of rows have unquoted semicolons in free text, which shifts every later column; skip them.
    return (row for row in rows if None not in row and None not in row.values())


def to_meta(project: dict, orgs: list[dict], today: dt.date) -> InnovationMeta:
    # The export doubles quotes inside some already-quoted fields.
    project = {key: value.replace('""', '"') for key, value in project.items()}
    lead = next((o for o in orgs if o["role"] == "coordinator"), orgs[0])
    found = sectors(" ".join([project["title"], project["keywords"], project["objective"]]))
    kind = institution_kind(lead)
    names = list(dict.fromkeys(o["name"].title() for o in orgs))
    evidence = [f"Projekt Horizon Europe nr {project['id']} ({project['fundingScheme']})",
                f"realizacja {project['startDate']} - {project['endDate']}"]
    if project["ecMaxContribution"]:
        evidence.append(f"wkład UE {float(project['ecMaxContribution'].replace(',', '.')):,.0f} EUR".replace(",", " "))
    if lead["role"] == "coordinator":
        evidence.append("polski koordynator")
    return InnovationMeta(
        id=f"cordis-{project['id']}",
        title=clip(f"{project['acronym']}: {project['title']}" if project["acronym"] else project["title"], 300),
        categories=found, primary_category=found[0],
        innovation_type=InnovationType.TECHNOLOGICAL, institution_type=kind, institution=clip(lead["name"].title(), 300),
        region=NUTS2.get(lead["nutsCode"][:4]), area="technologia",
        source_name="CORDIS, Komisja Europejska (Horizon Europe)",
        source_url=f"https://cordis.europa.eu/project/id/{project['id']}",
        imported_at=today, checked_at=today,
        card=InnovationCard(
            solution=clip(project["objective"]),
            novelty=clip("Keywords: " + project["keywords"]) if project["keywords"] else "",
            target_users=clip("Polscy partnerzy: " + ", ".join(names)),
            evidence=clip(", ".join(evidence) + "."),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip", help="Use an already downloaded CORDIS export")
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--region", help="Limit to one Polish voivodeship (by the lead organisation)")
    args = parser.parse_args()
    region = region_name(args.region)
    if args.region and not region:
        parser.error("Unknown Polish voivodeship")
    if args.zip:
        data = open(args.zip, "rb").read()
    else:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=300, follow_redirects=True) as client:
            response = client.get(URL)
            response.raise_for_status()
            data = response.content
    archive = zipfile.ZipFile(io.BytesIO(data))
    orgs: dict[str, list[dict]] = defaultdict(list)
    for org in read(archive, "organization.csv"):
        if org["country"] == "PL" and org["role"] in ("coordinator", "participant"):
            orgs[org["projectID"]].append(org)
    projects = [p for p in read(archive, "project.csv")
                if p["id"] in orgs and scheme(p["fundingScheme"]) in SCHEMES and p["status"] != "TERMINATED"
                and len(p["objective"]) >= 200]
    metas = [to_meta(p, orgs[p["id"]], dt.date.today()) for p in projects]
    if region:
        metas = [m for m in metas if m.region == region]
    by_id = {p["id"]: p for p in projects}

    def rank(meta: InnovationMeta):
        project = by_id[meta.id.removeprefix("cordis-")]
        coordinated = any(o["role"] == "coordinator" for o in orgs[project["id"]])
        return not coordinated, SCHEMES[scheme(project["fundingScheme"])], -int(project["startDate"].replace("-", "") or 0)

    kept = sorted(metas, key=rank)[:args.limit]
    if not kept:
        raise ValueError("No CORDIS projects found for the selected scope")
    print(f"CORDIS: {len(kept)} of {len(projects)} eligible Polish projects", file=sys.stderr)
    emit(kept)


assert scheme("HORIZON-EIC-ACC") == "EIC" and scheme("HORIZON-RIA") == "RIA"
assert NUTS2["PL82"] == "Podkarpackie" and len(set(NUTS2.values())) == 16

if __name__ == "__main__":
    main()
