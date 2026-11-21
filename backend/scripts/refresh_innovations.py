"""Fetch Radar sources and merge changed metadata through the knowledge API."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx

from import_deployments import records

SOURCES = ("deployments", "interreg", "radon", "cordis", "fundusze")
HERE = Path(__file__).resolve().parent


def fetch(source: str, region: str | None):
    if source == "deployments":
        result, failures = records()
        return [card.model_dump(mode="json") for card in result], failures
    cmd = [sys.executable, str(HERE / f"import_{source}.py")]
    if region:
        cmd.extend(["--region", region])
    # Keep the last published version when the source returns incomplete or invalid data.
    output = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True, timeout=2700)
    rows = json.loads(output.stdout)
    if not rows:
        raise ValueError("The source returned no records")
    return [item["meta"] for item in rows], 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=SOURCES, action="append", help="Repeat for multiple sources; default all")
    parser.add_argument("--region", help="Limit registry candidates to one voivodeship")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and count source records without writing")
    parser.add_argument("--api", default=f"http://127.0.0.1:{os.getenv('BACKEND_PORT', '8000')}")
    args = parser.parse_args()
    token = os.getenv("RADAR_ADMIN_TOKEN")
    if not token and not args.dry_run:
        parser.error("RADAR_ADMIN_TOKEN is required to publish")

    failed = 0
    with httpx.Client(base_url=args.api, headers={"X-Admin-Token": token or ""}, timeout=120) as client:
        for source in dict.fromkeys(args.source or SOURCES):
            try:
                entries, errors = fetch(source, args.region)
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                failed += 1
                print(f"{source}: source unavailable ({exc})", file=sys.stderr)
                continue
            if args.dry_run:
                confirmed = sum(entry.get("verification") == "potwierdzona" for entry in entries)
                print(f"{source}: {len(entries)} fetched, {confirmed} confirmed, {errors} errors")
            else:
                counts = dict.fromkeys(("created", "updated", "unchanged"), 0)
                for entry in entries:
                    innovation_id = entry.pop("id")
                    try:
                        path = f"/api/v1/knowledge/innovations/{innovation_id}/refresh"
                        for attempt in range(3):
                            response = client.put(path, json=entry)
                            if response.status_code != 429 or attempt == 2:
                                break
                            time.sleep(60)
                        response.raise_for_status()
                        counts[response.json()["status"]] += 1
                    except (httpx.HTTPError, ValueError, KeyError) as exc:
                        errors += 1
                        print(f"{innovation_id}: {exc}", file=sys.stderr)
                print(f"{source}: {counts['created']} created, {counts['updated']} updated, "
                      f"{counts['unchanged']} unchanged, {errors} errors")
            failed += errors
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
