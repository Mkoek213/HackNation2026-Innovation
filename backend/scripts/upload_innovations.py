"""
Upload innovations from a seed file to a running backend (PUT /api/v1/knowledge/innovations/{id}).

Goes through the same HTTP pipeline as the admin UI, so documents land in S3 and vectors in Qdrant.

Usage (from the repository root, after `set -a; . ./.env; set +a` so RADAR_ADMIN_TOKEN is exported):
    uv --project backend run python backend/scripts/upload_innovations.py
    uv --project backend run python backend/scripts/upload_innovations.py --only uprp-p-441234 interreg-cleanair
    uv --project backend run python backend/scripts/upload_innovations.py --dry-run

Seed format (every backend/data/seed/*.json, one file per source):
    [{"meta": InnovationMeta,
      "summary": "path/to/short-overview.pdf",         # one file: ranks the innovation, linked as "Krótko"
      "files": ["path/or/glob", ...],                  # full materials: cited evidence
      "exclude": ["filename glob", ...]}]
File paths are relative to --root (default: repository root). `meta` can be drafted with
the source importers (scripts/import_*.py), then reviewed; the service answers only from what is uploaded here.
"""
import argparse
import glob
import json
import mimetypes
import os
import sys
import time
from fnmatch import fnmatch
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_DIR = REPO_ROOT / "backend" / "data" / "seed"


def collect(root: Path, patterns: list[str], exclude: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        matches = sorted(Path(p) for p in glob.glob(str(root / pattern)))
        if not matches:
            print(f"  warning: nothing matches {pattern}", file=sys.stderr)
        files.extend(m for m in matches if m.is_file() and m not in files)
    return [f for f in files if not any(fnmatch(f.name, x) for x in exclude)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default=os.getenv("API", "http://localhost:8000"))
    parser.add_argument("--seed", type=Path, nargs="+", default=sorted(SEED_DIR.glob("*.json")),
                        help="Seed files (default: every backend/data/seed/*.json)")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--only", nargs="*", help="Innovation ids to upload")
    parser.add_argument("--dry-run", action="store_true", help="List files without uploading")
    args = parser.parse_args()

    token = os.getenv("RADAR_ADMIN_TOKEN")
    if not token and not args.dry_run:
        print("RADAR_ADMIN_TOKEN is not set (run: set -a; . ./.env; set +a)", file=sys.stderr)
        return 2

    entries = [entry for seed in args.seed for entry in json.loads(seed.read_text(encoding="utf-8"))]
    failed = 0
    with httpx.Client(base_url=args.api, timeout=httpx.Timeout(900, connect=10)) as client:
        for entry in entries:
            meta = entry["meta"]
            innovation_id = meta["id"]
            if args.only and innovation_id not in args.only:
                continue
            files = collect(args.root, entry.get("files", []), entry.get("exclude", []))
            summary = args.root / entry["summary"] if entry.get("summary") else None
            if summary is not None and not summary.is_file():
                print(f"  warning: summary not found: {entry['summary']}", file=sys.stderr)
                summary = None
            files = [f for f in files if f != summary]
            print(f"{innovation_id}: summary {summary.name if summary else '-'}, {len(files)} full files")
            for f in files:
                print(f"  - {f.relative_to(args.root)}")
            if args.dry_run:
                continue

            started = time.monotonic()
            handles = [open(f, "rb") for f in files]
            summary_handle = open(summary, "rb") if summary else None
            try:
                response = client.put(
                    f"/api/v1/knowledge/innovations/{innovation_id}",
                    headers={"X-Admin-Token": token},
                    # Sent as a plain form field: no curl-style ';' parsing issues.
                    data={"meta": json.dumps({k: v for k, v in meta.items() if k != "id"}, ensure_ascii=False)},
                    files=[("files", (f.name, h, mimetypes.guess_type(f.name)[0] or "application/octet-stream"))
                           for f, h in zip(files, handles)]
                    + ([("summary", (summary.name, summary_handle, mimetypes.guess_type(summary.name)[0]
                                     or "application/octet-stream"))] if summary else []),
                )
            finally:
                for h in handles + ([summary_handle] if summary_handle else []):
                    h.close()
            took = time.monotonic() - started
            if response.status_code == 200:
                body = response.json()
                print(f"  ok in {took:.0f}s: {body['chunks']} chunks, summary {body.get('summary_file')}, "
                      f"indexed {len(body['files'])}, "
                      f"skipped {body.get('skipped_files') or []}")
            else:
                failed += 1
                print(f"  FAILED {response.status_code} in {took:.0f}s: {response.text[:500]}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
