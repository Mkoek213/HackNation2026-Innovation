"""
Assess every catalog card against the five FAQ criteria through the knowledge API.

Cards already assessed with the current criteria version are skipped unless --force. Staff edits and
source-confirmed notes are preserved by the server-side merge. Run after upload_innovations.py.

Usage (from the repository root, backend running):
    set -a && . ./.env && set +a
    uv --project backend run python backend/scripts/assess_innovations.py --api "http://localhost:${BACKEND_PORT}"
    uv --project backend run python backend/scripts/assess_innovations.py --only cordis- --limit 20 --force
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.knowledge.taxonomy import CRITERIA_VERSION  # noqa: E402

PREFIX = "/api/v1/knowledge"


async def assess_one(client: httpx.AsyncClient, gate: asyncio.Semaphore, innovation_id: str) -> str | None:
    async with gate:
        for attempt in range(4):
            response = await client.post(f"{PREFIX}/innovations/{innovation_id}/assess")
            if response.status_code != 429 or attempt == 3:
                break
            await asyncio.sleep(20 * (attempt + 1))  # provider rate limit; other errors are reported at once
        if response.is_success:
            return None
        return f"{innovation_id}: HTTP {response.status_code} {response.text[:200]}"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default=f"http://127.0.0.1:{os.getenv('BACKEND_PORT', '8000')}")
    parser.add_argument("--only", default="", help="Assess only ids starting with this prefix")
    parser.add_argument("--limit", type=int, default=0, help="Stop after this many cards (0 = all)")
    parser.add_argument("--force", action="store_true", help="Reassess cards already on the current criteria")
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    token = os.getenv("RADAR_ADMIN_TOKEN")
    if not token:
        parser.error("RADAR_ADMIN_TOKEN is required")
    async with httpx.AsyncClient(base_url=args.api, headers={"X-Admin-Token": token}, timeout=180) as client:
        response = await client.get(f"{PREFIX}/innovations")
        response.raise_for_status()
        todo = [item["id"] for item in response.json() if item["id"].startswith(args.only)
                and (args.force or (item.get("assessment") or {}).get("criteria_version") != CRITERIA_VERSION)]
        todo = todo[:args.limit] if args.limit else todo
        print(f"Assessing {len(todo)} cards with {CRITERIA_VERSION}", file=sys.stderr)
        gate = asyncio.Semaphore(args.concurrency)
        errors = [e for e in await asyncio.gather(*(assess_one(client, gate, i) for i in todo)) if e]
    for error in errors:
        print(error, file=sys.stderr)
    print(f"Assessed {len(todo) - len(errors)} of {len(todo)} cards, {len(errors)} errors")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
