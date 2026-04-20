"""
Stage 3 — identification, verification, polish, corpus update.

Phase 8:  person identification (regionizer + matcher + bootstrap)
Phase 8b: post-diarization verification pass (short-turn reassignment)
Phase 9:  term-fix polish (via persons.polish_engine)
Phase 10: corpus update + voiceprint library update

Stamps `processed_at_db_state` on output so `--redo` can detect staleness.
"""
from __future__ import annotations

from pathlib import Path


def identify_speakers(raw_json_path: Path, acapella_path: Path, meta: "SessionMeta") -> dict:
    """Map pyannote clusters to participant ids; bootstrap new persons."""
    raise NotImplementedError


def run_verification(transcript: dict, acapella_path: Path) -> dict:
    """Short-turn reassignment pass. In-place update of segment speaker labels."""
    raise NotImplementedError


def polish(transcript: dict) -> dict:
    """Dispatch to persons.polish_engine (cli or api) per config.POLISH_ENGINE."""
    raise NotImplementedError


def update_voice_libraries(transcript: dict, acapella_path: Path) -> None:
    """Per-region running-mean centroid update for each participant."""
    raise NotImplementedError


def stamp_db_state(transcript: dict) -> dict:
    """Attach `processed_at_db_state` snapshot (per-person n_sessions + observed_regions)."""
    raise NotImplementedError


def finalize(transcript: dict, out_path: Path) -> None:
    """Write polished JSON via utils.atomic_write; append to corpus.json."""
    raise NotImplementedError


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from filename_parser import SessionMeta
