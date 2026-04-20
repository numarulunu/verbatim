"""
Vocality ASR — asyncio orchestrator.

Drives the 10-phase pipeline end-to-end. Supports resumable normal runs and
`--redo` mode for retroactive reprocessing as the voiceprint database matures.

Phases (see brief §6):
  1  vocal isolation          (stage1_isolate)
  2  session-metadata extract (filename_parser)
  3  pre-VAD                  (utils.silero_vad)
  4  CPU decode               (decode_worker)
  5  ASR                      (stage2_transcribe_diarize)
  6  alignment                (stage2_transcribe_diarize)
  7  diarization              (stage2_transcribe_diarize)
  8  person identification    (stage3_postprocess + persons.matcher/verifier)
  9  polish                   (persons.polish_engine)
 10  corpus index update      (persons.corpus)

GPU work is serialized via asyncio.Semaphore(1). CPU work runs through a
ProcessPoolExecutor pinned to P-cores.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Iterable


async def orchestrate(inputs: Iterable[Path], redo: bool = False) -> None:
    """Main async entrypoint. Runs all 10 phases across every input."""
    raise NotImplementedError


def discover_inputs(material_dir: Path) -> list[Path]:
    """Walk MATERIAL_DIR for audio/video sources matching supported extensions."""
    raise NotImplementedError


def preflight() -> None:
    """Validate disk space, GPU availability, HF_TOKEN, ffmpeg on PATH."""
    raise NotImplementedError


def select_redo_candidates(
    threshold: int | None = None,
    student: str | None = None,
    teacher: str | None = None,
    confidence_below: float | None = None,
    after: str | None = None,
    redo_all: bool = False,
) -> list[Path]:
    """Delegate to persons.redo for stale-DB-state candidate detection."""
    raise NotImplementedError


def build_arg_parser() -> argparse.ArgumentParser:
    """CLI surface: normal run vs --redo mode."""
    raise NotImplementedError


def main() -> None:
    """Script entrypoint — parses args and dispatches to orchestrate()."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
