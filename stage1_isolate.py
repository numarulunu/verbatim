"""
Stage 1 — vocal isolation.

Wraps `audio-separator` + MelBand Roformer. Output is written to
ACAPELLA_DIR/<file_id>.wav. Idempotent: files whose acapella already exists
are skipped.

Post-separation we apply a spectral gate (utils.audio_qc.spectral_gate) to
kill residual harmonic ghosts under SPECTRAL_GATE_DB — those cause Whisper
hallucinations on sustained sung regions over piano.

VRAM teardown via `teardown_separator()` MUST run before stage2 touches the
GPU. MelBand Roformer holds ~4 GB on the 1080 Ti and will OOM whisper if
left in memory.
"""
from __future__ import annotations

import logging
from pathlib import Path

from config import ACAPELLA_DIR, SEPARATOR_MODEL, SPECTRAL_GATE_DB
from filename_parser import file_id as fileid_from_meta
from filename_parser import parse as parse_filename
from utils.audio_qc import spectral_gate

log = logging.getLogger(__name__)

_separator = None


def _load_separator():
    global _separator
    if _separator is not None:
        return _separator
    from audio_separator.separator import Separator

    ACAPELLA_DIR.mkdir(parents=True, exist_ok=True)
    _separator = Separator(
        output_dir=str(ACAPELLA_DIR),
        output_format="WAV",
        sample_rate=16_000,
    )
    _separator.load_model(SEPARATOR_MODEL)
    log.info("loaded audio-separator (%s)", SEPARATOR_MODEL)
    return _separator


def acapella_path_for(source: Path) -> Path:
    """Return the destination acapella path for a given source."""
    fid = fileid_from_meta(parse_filename(source))
    return ACAPELLA_DIR / f"{fid}.wav"


def isolate_one(source: Path) -> Path:
    """
    Vocal-isolate one source. Skips the separator call if the output exists.

    Returns the path to the acapella WAV.
    """
    source = Path(source)
    target = acapella_path_for(source)
    if target.exists():
        log.info("acapella exists: %s - skipping stage 1", target.name)
        return target

    separator = _load_separator()
    fid = target.stem

    # output_names renames the Vocals stem to exactly `{fid}.wav` inside
    # ACAPELLA_DIR (the separator's output_dir). No post-hoc rename needed.
    separator.separate(str(source), {"Vocals": fid})

    if not target.exists():
        raise RuntimeError(
            f"separator ran but {target.name!r} was not produced under {ACAPELLA_DIR}"
        )

    # Delete every OTHER file the separator wrote for this source (Instrumental
    # stem, model-name-suffixed duplicates, etc.). Match on fid prefix so we
    # don't touch other sessions' outputs.
    for leftover in ACAPELLA_DIR.glob(f"{fid}_*"):
        try:
            leftover.unlink()
        except OSError as exc:
            log.warning("could not remove secondary stem %s: %s", leftover.name, exc)

    _apply_post_gate(target)
    return target


def isolate_batch(sources: list[Path]) -> list[Path]:
    """
    Vocal-isolate many sources sequentially (model stays loaded).

    Returns the list of output paths, in the same order as `sources`. Files
    whose acapella already exists are included in the result without re-running.
    """
    outputs: list[Path] = []
    for src in sources:
        try:
            outputs.append(isolate_one(src))
        except Exception as exc:  # noqa: BLE001
            # One bad file does not abort the batch (brief §3).
            log.error("stage 1 failed for %s: %s", src, exc)
    return outputs


def _apply_post_gate(acapella: Path) -> None:
    """Apply the SPECTRAL_GATE_DB cleanup in place, via soundfile round-trip."""
    import numpy as np
    import soundfile as sf

    audio, sr = sf.read(str(acapella), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1).astype(np.float32)
    gated = spectral_gate(audio, sr=sr, floor_db=SPECTRAL_GATE_DB)
    sf.write(str(acapella), gated, sr, subtype="PCM_16")


def teardown_separator() -> None:
    """Release the separator and its VRAM. Must run before stage 2 starts."""
    global _separator
    if _separator is None:
        return
    _separator = None
    try:
        import gc
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
