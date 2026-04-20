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


def cmd_register(args: argparse.Namespace) -> int:
    """Create a new person. Second person with same display_name needs --disambiguator."""
    raise NotImplementedError


def cmd_list(args: argparse.Namespace) -> int:
    """Print every person with session counts and observed regions."""
    raise NotImplementedError


def cmd_inspect(args: argparse.Namespace) -> int:
    """Full metadata dump for <id>, including voiceprint centroid summary."""
    raise NotImplementedError


def cmd_collisions(args: argparse.Namespace) -> int:
    """List all person pairs whose universal cosine >COLLISION_THRESHOLD."""
    raise NotImplementedError


def cmd_confirm(args: argparse.Namespace) -> int:
    """Mark a session-id as human-approved; bypasses first-3-sessions gate."""
    raise NotImplementedError


def cmd_edit(args: argparse.Namespace) -> int:
    """Update voice_type, fach, disambiguator, or default_role."""
    raise NotImplementedError


def cmd_rename(args: argparse.Namespace) -> int:
    """Rename an id, rewriting all transcripts + corpus.json references."""
    raise NotImplementedError


def cmd_merge(args: argparse.Namespace) -> int:
    """Merge two person records into one, combining voice libraries."""
    raise NotImplementedError


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct the subparser tree."""
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
