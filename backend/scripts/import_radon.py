"""
Import research projects of Polish institutions from RAD-on (POL-on) as candidates.

Source: the RAD-on open data API of Ośrodek Przetwarzania Informacji (https://radon.nauka.gov.pl),
no key required. Active institutions are listed first, then the
projects each one reports. Project managers are public RAD-on data and are kept as authors.
Projects without a Polish abstract, or that ended before --since, are skipped.

Usage (from backend/):
    uv run python scripts/import_radon.py > data/seed/radon.json
    uv run python scripts/import_radon.py --since 2022-01-01 --limit 150
"""
import argparse
from collections import defaultdict
import datetime as dt
import sys
import time

import httpx

from import_common import USER_AGENT, application_area, clip, emit, innovation_type, region_name, sectors, slug
from app.modules.knowledge.schemas import Author, InnovationCard, InnovationMeta
from app.modules.knowledge.taxonomy import InnovationType, InstitutionType

API = "https://radon.nauka.gov.pl/opendata/polon"
PAGE = 100
PAUSE_SECONDS = 0.5  # Be gentle with the public API.
SOCIAL_DISCIPLINES = ("humanistyczn", "społeczn", "teologi", "prawn", "ekonomi", "pedagog", "psycholog", "sztuk")


def pages(client: httpx.Client, path: str, **params):
    token = None
    while True:
        response = client.get(f"{API}/{path}", params={"resultNumbers": PAGE, **params, **({"token": token} if token else {})})
        response.raise_for_status()
        data = response.json()
        yield from data["results"]
        token = data["pagination"].get("token")
        if not data["results"] or not token or len(data["results"]) < PAGE:
            return
        time.sleep(PAUSE_SECONDS)


def to_meta(project: dict, institution: str, region: str, today: dt.date) -> InnovationMeta:
    disciplines = " ".join(d.get("disciplineName", "") for d in project.get("disciplines") or [] if isinstance(d, dict))
    text = " ".join(filter(None, [project.get("projectTitlePl"), project.get("keywords"), disciplines, project.get("projectAbstractPl")]))
    found = sectors(text)
    social = any(word in disciplines.lower() for word in SOCIAL_DISCIPLINES)
    kind = innovation_type(text, InnovationType.SOCIAL if social else InnovationType.TECHNOLOGICAL)
    funders = ", ".join(dict.fromkeys(f["financingInstitutionName"] for f in project.get("financingInstitutions") or [] if f.get("financingInstitutionName")))
    number = project.get("projectNumber") or ""
    evidence = [f"Projekt badawczy nr {number}" if number else "Projekt badawczy"]
    if project.get("projectStartDate") and project.get("projectEndDate"):
        evidence.append(f"realizacja {project['projectStartDate']} - {project['projectEndDate']}")
    if funders:
        evidence.append(f"finansowanie: {funders}")
    if project.get("namePriority"):
        evidence.append(f"konkurs: {project['namePriority']}")
    authors = [Author(name=" ".join(filter(None, [m.get("firstName"), m.get("lastName")])), affiliation=m.get("institutionName"))
               for m in project.get("projectManagers") or [] if m.get("lastName")]
    return InnovationMeta(
        id="radon-" + (slug(number) or project["projectUuid"].lower()),
        title=clip(project["projectTitlePl"], 300),
        categories=found, primary_category=found[0],
        innovation_type=kind,
        institution_type=InstitutionType.UNIVERSITY, institution=institution,
        region=region, area=application_area(kind, InstitutionType.UNIVERSITY),
        authors=authors[:10],
        source_name="RAD-on (POL-on), Ośrodek Przetwarzania Informacji", source_url="https://radon.nauka.gov.pl/dane/projekty",
        imported_at=today, checked_at=today,
        card=InnovationCard(
            solution=clip(project.get("projectAbstractPl")),
            novelty=clip("Słowa kluczowe: " + project["keywords"]) if project.get("keywords") else "",
            evidence=clip(", ".join(evidence) + "."),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", type=dt.date.fromisoformat, default=dt.date(2022, 1, 1),
                        help="Skip projects that ended before this date (default 2022-01-01)")
    parser.add_argument("--limit", type=int, default=20, help="Keep at most this many newest projects per voivodeship")
    parser.add_argument("--region", help="Limit to one Polish voivodeship")
    args = parser.parse_args()
    region = region_name(args.region)
    if args.region and not region:
        parser.error("Unknown Polish voivodeship")
    if args.limit < 1:
        parser.error("--limit must be positive")
    today = dt.date.today()
    metas = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60) as client:
        institutions = [(i, name) for i in pages(client, "institutions")
                        if (name := region_name(i.get("voivodeship"))) and (not region or name == region)
                        and i.get("status") == "Działająca"
                        and i.get("iKindName") in {"Uczelnia publiczna", "Instytucja naukowa"}]
        print(f"RAD-on: reading projects from {len(institutions)} institutions", file=sys.stderr)
        for institution, name in institutions:
            for project in pages(client, "projects", entityShowingAchievementsUuid=institution["institutionUuid"]):
                end = project.get("projectEndDate")
                if not project.get("projectAbstractPl") or not project.get("projectTitlePl") or (end and end < args.since.isoformat()):
                    continue
                meta = to_meta(project, institution["name"], name, today)
                metas.setdefault(meta.id, (end or "9999", meta))
            time.sleep(PAUSE_SECONDS)
    by_region = defaultdict(list)
    for end, meta in metas.values():
        by_region[meta.region].append((end, meta))
    newest = [meta for group in by_region.values()
              for _, meta in sorted(group, key=lambda pair: (pair[0], pair[1].id), reverse=True)[:args.limit]]
    print(f"RAD-on: {len(newest)} of {len(metas)} eligible projects from {len(institutions)} institutions", file=sys.stderr)
    emit(newest)


if __name__ == "__main__":
    main()
