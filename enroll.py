"""
Person registry CLI.

Subcommands:
  register    — create a new person record (refuses same-display-name
                collisions unless --disambiguator given)
  list        — show all registered persons with session counts
  inspect     — full metadata + voiceprint summary for one person
  collisions  — flagged cross-person voiceprint similarity pairs
  confirm     — manually approve an early-session voiceprint update
  edit        — change voice_type, fach, disambiguator
  rename      — safely rename <id> across transcripts + corpus.json
  merge       — merge two person records (accidental duplicates)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from persons import matcher, registry
from persons.schema import render_display, total_sessions

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

def cmd_register(args: argparse.Namespace) -> int:
    try:
        record = registry.register_new(
            id_=args.id,
            display_name=args.name,
            default_role=args.default_role,
            disambiguator=args.disambiguator,
            voice_type=args.voice_type,
            fach=args.fach,
        )
    except registry.DuplicateDisplayNameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"registered: {record.id}  ({render_display(record)}, {record.default_role})")
    return 0


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    people = registry.list_all()
    if not people:
        print("no persons registered yet.")
        return 0
    print(f"{'id':<20} {'display':<28} {'role':<8} {'voice':<10} sessions  regions")
    print("-" * 96)
    for p in people:
        regions = ",".join(p.observed_regions) or "-"
        print(
            f"{p.id:<20} {render_display(p):<28} {p.default_role:<8} "
            f"{(p.voice_type or '-'):<10} {total_sessions(p):<8}  {regions}"
        )
    return 0


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------

def cmd_inspect(args: argparse.Namespace) -> int:
    try:
        person = registry.load(args.id)
    except registry.PersonNotFoundError:
        print(f"error: no person with id {args.id!r}", file=sys.stderr)
        return 2
    pdir = matcher.person_dir(person.id)
    centroids = sorted(p.name for p in pdir.glob("*.npy")) if pdir.exists() else []
    payload = {
        "record": {
            "id": person.id,
            "display_name": person.display_name,
            "disambiguator": person.disambiguator,
            "default_role": person.default_role,
            "voice_type": person.voice_type,
            "fach": person.fach,
            "n_sessions_as_teacher": person.n_sessions_as_teacher,
            "n_sessions_as_student": person.n_sessions_as_student,
            "total_hours": round(person.total_hours, 2),
            "first_seen": person.first_seen,
            "last_updated": person.last_updated,
            "observed_regions": person.observed_regions,
            "region_session_counts": person.region_session_counts,
            "pitch_range_hz": list(person.pitch_range_hz) if person.pitch_range_hz else None,
            "collisions": person.collisions,
        },
        "voiceprint_files": centroids,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# collisions
# ---------------------------------------------------------------------------

def cmd_collisions(args: argparse.Namespace) -> int:
    pairs = matcher.check_collisions()
    if not pairs:
        print("no collisions above threshold.")
        return 0
    print("id_a                 id_b                 cosine")
    print("-" * 56)
    for a, b, cos in pairs:
        print(f"{a:<20} {b:<20} {cos:.3f}")
    return 0


# ---------------------------------------------------------------------------
# confirm
# ---------------------------------------------------------------------------

def cmd_confirm(args: argparse.Namespace) -> int:
    try:
        person = registry.load(args.id)
    except registry.PersonNotFoundError:
        print(f"error: no person with id {args.id!r}", file=sys.stderr)
        return 2
    marker = f"confirmed:{args.session_id}"
    if marker in person.collisions:
        print(f"already confirmed: {args.session_id}")
        return 0
    person.collisions.append(marker)
    registry.save(person)
    print(f"confirmed voiceprint update for {person.id} session {args.session_id}")
    return 0


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------

def cmd_edit(args: argparse.Namespace) -> int:
    try:
        person = registry.load(args.id)
    except registry.PersonNotFoundError:
        print(f"error: no person with id {args.id!r}", file=sys.stderr)
        return 2
    touched = []
    if args.voice_type is not None:
        person.voice_type = args.voice_type
        touched.append("voice_type")
    if args.fach is not None:
        person.fach = args.fach
        touched.append("fach")
    if args.disambiguator is not None:
        person.disambiguator = args.disambiguator or None
        touched.append("disambiguator")
    if args.default_role is not None:
        if args.default_role not in ("teacher", "student"):
            print("error: default_role must be 'teacher' or 'student'", file=sys.stderr)
            return 2
        person.default_role = args.default_role
        touched.append("default_role")
    if not touched:
        print("nothing to edit (pass at least one field)")
        return 1
    registry.save(person)
    print(f"edited {person.id}: {', '.join(touched)}")
    return 0


# ---------------------------------------------------------------------------
# rename / merge
# ---------------------------------------------------------------------------

def cmd_rename(args: argparse.Namespace) -> int:
    try:
        registry.rename(args.old_id, args.new_id)
    except (registry.PersonNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"renamed {args.old_id} -> {args.new_id}")
    print("transcripts still reference the old id; run `python run.py --redo --all` to rewrite them.")
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    try:
        registry.merge(args.id1, args.id2, keep=args.keep)
    except (registry.PersonNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"merged {args.id1} + {args.id2} -> {args.keep}")
    print("voiceprint centroids NOT averaged; run `python run.py --redo --all` to rebuild.")
    return 0


# ---------------------------------------------------------------------------
# Argparse tree
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verbatim person registry.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("register", help="Create a new person record.")
    p.add_argument("--id", required=True, help="ASCII lowercase id, e.g. 'madalina_r'")
    p.add_argument("--name", required=True, help="Display name with diacritics")
    p.add_argument("--default-role", choices=("teacher", "student"), default="student")
    p.add_argument("--disambiguator", default=None,
                   help="Suffix rendered after name when two persons share display_name")
    p.add_argument("--voice-type", default=None,
                   help="bass | baritone | tenor | alto | mezzo | soprano")
    p.add_argument("--fach", default=None, help="lirico | drammatico | leggero | spinto | buffo")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("list", help="Show all registered persons.")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("inspect", help="Full metadata + voiceprint summary for <id>.")
    p.add_argument("id")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("collisions",
                       help="List person-pairs whose universal cosine > COLLISION_THRESHOLD.")
    p.set_defaults(func=cmd_collisions)

    p = sub.add_parser("confirm",
                       help="Approve an early-session voiceprint update (bypasses first-3 gate).")
    p.add_argument("id")
    p.add_argument("session_id")
    p.set_defaults(func=cmd_confirm)

    p = sub.add_parser("edit", help="Update voice_type, fach, disambiguator, or default_role.")
    p.add_argument("id")
    p.add_argument("--voice-type", default=None)
    p.add_argument("--fach", default=None)
    p.add_argument("--disambiguator", default=None,
                   help="Set (or pass empty string to clear) the disambiguator")
    p.add_argument("--default-role", default=None, choices=("teacher", "student"))
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("rename", help="Rename an id.")
    p.add_argument("old_id")
    p.add_argument("new_id")
    p.set_defaults(func=cmd_rename)

    p = sub.add_parser("merge", help="Merge two accidental duplicates.")
    p.add_argument("id1")
    p.add_argument("id2")
    p.add_argument("--keep", required=True,
                   help="Which id to keep (must be one of id1/id2)")
    p.set_defaults(func=cmd_merge)

    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_arg_parser().parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
