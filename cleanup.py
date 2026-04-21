"""
Remove intermediate files after final outputs are verified.

Only deletes entries under 01_acapella/ and 02_raw_json/ whose corresponding
03_polished/<file_id>.json exists AND validates against the output schema.
Never touches _voiceprints/, corpus.json, session_map.json, or Material/.

Also purges orphaned `*.tmp` files (atomic-write leftovers from crashes).
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from config import (
    ACAPELLA_DIR,
    POLISHED_DIR,
    RAW_JSON_DIR,
)
from utils.atomic_write import purge_tmp_siblings

log = logging.getLogger(__name__)

_REQUIRED_TOP_KEYS = frozenset(("file_id", "language", "participants", "segments"))


def verify_polished(polished_path: Path) -> bool:
    """Schema-validate a polished JSON. Returns True iff safe to clean upstream."""
    try:
        with open(polished_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    if not _REQUIRED_TOP_KEYS.issubset(data.keys()):
        return False
    segs = data.get("segments")
    if not isinstance(segs, list) or not segs:
        return False
    return True


def find_safe_to_delete() -> list[Path]:
    """Return intermediate files whose polished counterpart exists AND validates."""
    if not POLISHED_DIR.exists():
        return []
    out: list[Path] = []
    for polished in sorted(POLISHED_DIR.glob("*.json")):
        file_id = polished.stem
        if not verify_polished(polished):
            log.warning(
                "polished %s fails schema - skipping cleanup for this file",
                polished.name,
            )
            continue
        acap = ACAPELLA_DIR / f"{file_id}.wav"
        if acap.exists():
            out.append(acap)
        for raw in RAW_JSON_DIR.glob(f"{file_id}.*.json"):
            out.append(raw)
    return out


def delete(paths: list[Path], dry_run: bool = False) -> None:
    """Remove given paths; in dry_run, only log."""
    for p in paths:
        if dry_run:
            log.info("would delete %s", p)
            continue
        try:
            p.unlink()
            log.info("deleted %s", p)
        except OSError as exc:
            log.error("delete %s failed: %s", p, exc)


def purge_orphan_tmps(dry_run: bool = False) -> int:
    """Scan intermediate dirs for `.tmp` leftovers from crashed atomic writes."""
    if dry_run:
        # Count without removing.
        total = 0
        for d in (ACAPELLA_DIR, RAW_JSON_DIR, POLISHED_DIR):
            if d.exists():
                total += sum(1 for _ in d.glob("*.tmp"))
        if total:
            log.info("would purge %d orphaned .tmp file(s)", total)
        return total
    total = 0
    for d in (ACAPELLA_DIR, RAW_JSON_DIR, POLISHED_DIR):
        total += purge_tmp_siblings(d)
    if total:
        log.info("purged %d orphaned .tmp file(s)", total)
    return total


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Remove intermediate files after polished outputs verify."
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be deleted, don't actually delete",
    )
    p.add_argument(
        "--skip-tmp-purge",
        action="store_true",
        help="don't purge orphan .tmp files from crashed atomic writes",
    )
    return p


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_arg_parser().parse_args()

    targets = find_safe_to_delete()
    if targets:
        log.info(
            "%d intermediate file(s) safe to delete.", len(targets)
        )
        delete(targets, dry_run=args.dry_run)
    else:
        log.info("nothing to clean up from intermediates.")

    if not args.skip_tmp_purge:
        purge_orphan_tmps(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
