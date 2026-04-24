"""
Verbatim ASR — asyncio orchestrator.

Normal mode:
  1. preflight (disk, HF token, ffmpeg, GPU capability)
  2. discover inputs in MATERIAL_DIR
  3. stage 1: batch vocal isolation (releases VRAM when done)
  4. per-file (asyncio, GPU serialized via Semaphore):
     - decode to 16 kHz mono float32
     - silero VAD pre-filter
     - stage 2: whisper transcribe + wav2vec2 align + pyannote diarize
     - stage 2b: cluster embeddings
     - stage 3: identify + verify + polish + update voice libs + write

--redo mode:
  1. find candidates via persons.redo (threshold / student / teacher /
     confidence-below / after / all)
  2. for each candidate: reuse cached acapella + raw_json, re-run
     identification + polish + corpus update only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
    ACAPELLA_DIR,
    HF_TOKEN,
    LOG_DIR,
    MATERIAL_DIR,
    MIN_FREE_DISK_GB,
    PIPELINE_DIRS,
    POLISH_ENGINE,
    POLISHED_DIR,
    RAW_JSON_DIR,
    REDO_CONFIDENCE_FLOOR,
    REDO_THRESHOLD_SESSIONS,
)
from filename_parser import FilenameParseError, file_id as fileid_from_meta, parse as parse_filename
from hw_clamp import pin_to_p_cores, verify_cuda_compute_capability
from utils import cancellation
from utils.atomic_write import atomic_write_json
from utils.reporter import NULL_REPORTER, Reporter

log = logging.getLogger(__name__)


# Phase-index lookup shared with ipc_protocol. 1-based so phase events
# match the protocol's `phase_index` field naturally.
def _phase_index(name: str) -> int:
    from ipc_protocol import PHASE_NAMES
    return PHASE_NAMES.index(name) + 1


async def _timed_phase(reporter: Reporter, file_index: int, name: str, coro):
    """Emit phase_started / phase_complete around an async step.

    The awaited coroutine may raise. On exception we skip phase_complete
    so the caller sees a partial sequence — debugging signal that that
    specific phase failed.
    """
    import time as _time
    reporter.phase_started(file_index=file_index, phase=name, phase_index=_phase_index(name))
    t0 = _time.monotonic()
    result = await coro
    reporter.phase_complete(file_index=file_index, phase=name, elapsed_s=_time.monotonic() - t0)
    return result


def _timed_phase_sync(reporter: Reporter, file_index: int, name: str, fn, *args, **kwargs):
    """Synchronous counterpart — for inline stage calls inside worker threads."""
    import time as _time
    reporter.phase_started(file_index=file_index, phase=name, phase_index=_phase_index(name))
    t0 = _time.monotonic()
    result = fn(*args, **kwargs)
    reporter.phase_complete(file_index=file_index, phase=name, elapsed_s=_time.monotonic() - t0)
    return result

SUPPORTED_EXTS = frozenset((".mp4", ".m4a", ".mp3", ".wav", ".webm", ".ogg", ".flac"))


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def preflight(skip_disk_check: bool = False) -> None:
    """Validate environment before touching any file."""
    for d in PIPELINE_DIRS:
        d.mkdir(parents=True, exist_ok=True)

    if not HF_TOKEN:
        raise RuntimeError("HUGGINGFACE_TOKEN / HF_TOKEN must be set")

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH (winget install Gyan.FFmpeg)")
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe not found on PATH")

    usage = shutil.disk_usage(str(MATERIAL_DIR.parent))
    free_gb = usage.free / (1024 ** 3)
    if free_gb < MIN_FREE_DISK_GB and not skip_disk_check:
        raise RuntimeError(
            f"insufficient disk: {free_gb:.1f} GB free, need {MIN_FREE_DISK_GB} GB "
            f"(the 400 GB target sizes the full ~320h backlog; use --skip-disk-check "
            f"for small test runs)"
        )
    if skip_disk_check:
        log.info("disk check skipped (%.1f GB free)", free_gb)

    # GPU capability probe — logs a warning if not Pascal, but does not abort
    # (the pipeline will still run, just with potentially wrong compute_type
    # choice on newer cards — see hw_clamp docstring).
    try:
        verify_cuda_compute_capability()
    except RuntimeError as exc:
        log.warning("GPU check failed: %s", exc)

    pin_to_p_cores()

    # Reconcile any orphan polished JSONs missing from corpus.json (crash
    # recovery for the stage3.finalize two-write window — see _backlog.md
    # SMAC Finding #4).
    from persons.corpus import reconcile_from_polished
    added = reconcile_from_polished()
    if added:
        log.warning("corpus reconciler: re-indexed %d orphan polished transcript(s)", added)

    # Install the hf_hub use_auth_token shim early so the redo path (which
    # skips stage 2 / load_diarizer) still has it when load_embedder runs.
    from utils.hf_compat import patch_hf_hub_use_auth_token
    patch_hf_hub_use_auth_token()


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_inputs(material_dir: Path) -> list[Path]:
    """Walk MATERIAL_DIR recursively for supported-extension audio/video files."""
    if not material_dir.exists():
        return []
    results: list[Path] = []
    for p in sorted(material_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            results.append(p)
    return results


def needs_processing(source: Path) -> bool:
    """True if no polished transcript exists for this source yet."""
    try:
        meta = parse_filename(source)
    except FilenameParseError:
        return False
    fid = fileid_from_meta(meta)
    return not (POLISHED_DIR / f"{fid}.json").exists()


# ---------------------------------------------------------------------------
# Normal-mode pipeline per file
# ---------------------------------------------------------------------------

async def _process_one(
    source: Path,
    acapella: Path,
    gpu_sem: asyncio.Semaphore,
    reporter: Reporter | None = None,
    file_index: int = 0,
) -> bool:
    """Return True on success. Errors are logged and contained.

    `reporter` lets the Electron daemon surface per-phase progress. CLI
    callers leave it None and get the silent NullReporter.
    """
    reporter = reporter or NULL_REPORTER
    try:
        meta = parse_filename(source)
    except FilenameParseError as exc:
        log.error("skipping %s: %s", source.name, exc)
        return False
    fid = fileid_from_meta(meta)

    try:
        # Phases 3, 4 — CPU-only, run off the GPU semaphore.
        cancellation.cancel_check()
        audio = await _timed_phase(
            reporter, file_index, "decode",
            asyncio.to_thread(_decode_acapella, acapella),
        )
        cancellation.cancel_check()
        vad_spans = await _timed_phase(
            reporter, file_index, "vad",
            asyncio.to_thread(_run_vad, audio),
        )

        # Phases 5, 6, 7 — GPU-serialized. _transcribe_align_diarize emits
        # its own asr / alignment / diarization phase events inline.
        cancellation.cancel_check()
        async with gpu_sem:
            labeled, cluster_emb = await asyncio.to_thread(
                _transcribe_align_diarize, audio, meta.language, vad_spans,
                reporter, file_index,
            )

        # Phases 8, 8b, 9, 10 — CPU + LLM. _finalize emits identification /
        # verification / polish / corpus_update phase events.
        cancellation.cancel_check()
        await asyncio.to_thread(
            _finalize, source, acapella, audio, labeled, cluster_emb, meta, fid,
            reporter, file_index,
        )
        log.info("done: %s", fid)
        return True
    except cancellation.CancelledError:
        # Propagate — the batch handler breaks the outer loop.
        raise
    except Exception as exc:  # noqa: BLE001 — orchestrator must contain per-file errors
        log.exception("failed: %s -> %s", fid, exc)
        return False


def _decode_acapella(acapella: Path):
    import soundfile as sf
    audio, sr = sf.read(str(acapella), dtype="float32")
    if audio.ndim > 1:
        import numpy as np
        audio = audio.mean(axis=1).astype(np.float32)
    if sr != 16000:
        # Resample if the acapella wasn't written at 16 k.
        import numpy as np
        import librosa
        audio = librosa.resample(audio, orig_sr=sr, target_sr=16000).astype(np.float32)
    return audio


def _run_vad(audio):
    from utils import silero_vad
    return silero_vad.speech_timestamps(audio, sr=16000)


def _transcribe_align_diarize(
    audio,
    language: str,
    vad_spans,
    reporter: Reporter | None = None,
    file_index: int = 0,
):
    import stage2_transcribe_diarize as st2
    reporter = reporter or NULL_REPORTER

    raw = _timed_phase_sync(
        reporter, file_index, "asr",
        st2.transcribe, audio, language=language, vad_timestamps=vad_spans,
    )
    aligned = _timed_phase_sync(
        reporter, file_index, "alignment",
        st2.align, audio, raw["segments"], language,
    )

    reporter.phase_started(file_index=file_index, phase="diarization",
                           phase_index=_phase_index("diarization"))
    import time as _time
    t0 = _time.monotonic()
    diar = st2.diarize(audio)
    labeled = st2.attach_speaker_labels(aligned, diar)
    cluster_emb = st2.cluster_embeddings_from_segments(labeled, audio)
    reporter.phase_complete(file_index=file_index, phase="diarization",
                            elapsed_s=_time.monotonic() - t0)
    return labeled, cluster_emb


def _finalize(
    source: Path,
    acapella: Path,
    audio,
    labeled_segments: list[dict],
    cluster_emb: dict[str, Any],
    meta,
    fid: str,
    reporter: Reporter | None = None,
    file_index: int = 0,
) -> None:
    import stage3_postprocess as st3
    reporter = reporter or NULL_REPORTER

    identified, label_to_person = _timed_phase_sync(
        reporter, file_index, "identification",
        st3.identify_speakers, labeled_segments, cluster_emb, audio, 16000, meta,
    )
    # Phase 3 (2026-04-24 plan): tag region per segment, branch sung from
    # spoken, run sung handler + word-level re-attribution before polish. The
    # sung branch keeps its segments out of verification and polish entirely
    # — sustained vowels have no phoneme boundaries for either pass to use.
    # These sub-phases are internal — not surfaced to the renderer's phase
    # progress, so they call the helpers directly rather than through
    # _timed_phase_sync (which would require expanding ipc_protocol.PHASE_NAMES).
    annotated = st3.annotate_regions(identified, audio, 16000)
    spoken, sung = st3.split_sung_and_spoken(annotated)
    sung = st3.handle_sung_segments(sung, audio, 16000, label_to_person)
    spoken = st3.reattribute_spoken_words(spoken, audio, 16000, label_to_person)
    verified = _timed_phase_sync(
        reporter, file_index, "verification",
        st3.run_verification, spoken, cluster_emb, label_to_person, audio, 16000,
    )
    polished = _timed_phase_sync(
        reporter, file_index, "polish",
        st3.polish, verified, meta.language,
    )
    # Re-merge sung segments into the polished list so the corpus + final
    # transcript carry both. Sort by start time so the file remains chronological.
    polished = sorted(list(polished) + list(sung), key=lambda s: float(s.get("start", 0.0)))

    reporter.phase_started(file_index=file_index, phase="corpus_update",
                           phase_index=_phase_index("corpus_update"))
    import time as _time
    t0 = _time.monotonic()
    st3.update_voice_libraries(polished, label_to_person, audio, 16000, meta)

    from utils.audio_qc import overlap_ratio, source_codec_info
    # Overlap ratio from the same diarization; we reconstruct a minimal
    # "two-cluster activity" from labeled_segments since we don't keep the
    # raw pyannote DataFrame past stage 2.
    ov = _approximate_overlap_ratio(labeled_segments)
    codec = source_codec_info(source)

    transcript = {
        "file_id": fid,
        "date": meta.date,
        "language": meta.language,
        "duration_s": float(len(audio)) / 16000.0,
        "overlap_ratio": ov,
        "source_codec": codec.get("codec"),
        "source_bitrate": codec.get("bitrate"),
        "mfa_aligned": False,
        "participants": [
            {"id": p.id, "name": _display(p), "role": _role_for(p, meta)}
            for p in label_to_person.values()
        ],
        "cluster_embeddings": {k: v.tolist() for k, v in cluster_emb.items()},
        "segments": polished,
    }
    st3.stamp_db_state(transcript)
    st3.finalize(transcript, POLISHED_DIR / f"{fid}.json")
    reporter.phase_complete(file_index=file_index, phase="corpus_update",
                            elapsed_s=_time.monotonic() - t0)


def _display(person) -> str:
    from persons.schema import render_display
    return render_display(person)


def _role_for(person, meta) -> str | None:
    if person.id == meta.teacher_id:
        return "teacher"
    if person.id == meta.student_id:
        return "student"
    return person.default_role


def _approximate_overlap_ratio(segments: list[dict]) -> float:
    """Cheap overlap approximation from attach_speaker_labels output."""
    by_cluster: dict[str, list[tuple[float, float]]] = {}
    for s in segments:
        lbl = s.get("cluster_label")
        if not lbl:
            continue
        by_cluster.setdefault(lbl, []).append((float(s["start"]), float(s["end"])))
    from utils.audio_qc import overlap_ratio
    class _Fake:
        def iterrows(self):
            for lbl, spans in by_cluster.items():
                for a, b in spans:
                    yield None, {"start": a, "end": b, "speaker": lbl}
    if not segments:
        return 0.0
    total_s = float(max(s["end"] for s in segments))
    return overlap_ratio(_Fake(), total_s)


# ---------------------------------------------------------------------------
# Normal mode driver
# ---------------------------------------------------------------------------

async def orchestrate_normal(skip_disk_check: bool = False) -> int:
    preflight(skip_disk_check=skip_disk_check)
    inputs = discover_inputs(MATERIAL_DIR)
    inputs = [p for p in inputs if needs_processing(p)]
    if not inputs:
        log.info("nothing to do - all inputs already have polished transcripts.")
        return 0

    log.info("found %d file(s) to process.", len(inputs))

    # Phase 1 — batch vocal isolation, then release VRAM.
    import stage1_isolate
    pairs: list[tuple[Path, Path]] = []
    for src in inputs:
        try:
            acap = stage1_isolate.isolate_one(src)
            pairs.append((src, acap))
        except Exception as exc:  # noqa: BLE001
            log.error("stage 1 failed for %s: %s", src.name, exc)
    stage1_isolate.teardown_separator()

    # Phase 3-10 — sequential per file. The brief allows parallel CPU phases
    # with a GPU semaphore, but our silero/whisperx/pyannote singletons hold
    # non-thread-safe internal state. Sequential is correct and plenty fast
    # for a 320h backlog at ~3-5 min/file.
    gpu_sem = asyncio.Semaphore(1)
    results: list[bool] = []
    for src, acap in pairs:
        try:
            ok_one = await _process_one(src, acap, gpu_sem)
            results.append(ok_one)
        except Exception as exc:  # noqa: BLE001 - per-file error containment
            log.exception("uncaught failure on %s: %s", src.name, exc)
            results.append(False)
    ok = sum(1 for r in results if r is True)
    log.info("complete: %d ok / %d attempted.", ok, len(results))
    return 0 if ok == len(results) else 1


# ---------------------------------------------------------------------------
# Redo mode
# ---------------------------------------------------------------------------

async def orchestrate_redo(args: argparse.Namespace) -> int:
    preflight(skip_disk_check=args.skip_disk_check)
    from persons import redo as redo_mod

    candidates = redo_mod.find_candidates(
        threshold=args.threshold,
        student=args.student,
        teacher=args.teacher,
        confidence_below=args.confidence_below,
        after=args.after,
        redo_all=args.all,
    )
    if not candidates:
        log.info("redo: no candidates match.")
        return 0
    log.info("redo: %d candidate(s) match.", len(candidates))
    if args.dry_run:
        for c in candidates:
            print(c.name)
        return 0

    ok = 0
    for polished in candidates:
        try:
            await asyncio.to_thread(_redo_one, polished)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            log.exception("redo failed for %s: %s", polished.name, exc)
    log.info("redo complete: %d ok / %d attempted.", ok, len(candidates))
    return 0 if ok == len(candidates) else 1


def _redo_one(polished_path: Path) -> None:
    """
    Re-run Phase 8-10 using cached Phase 1-7 artifacts.

    The polished JSON contains cluster_embeddings + segments, so we can
    re-identify without rerunning whisper / pyannote. Phase 10 rewrites the
    voiceprint libraries against the new attribution.
    """
    import numpy as np
    import stage3_postprocess as st3

    with open(polished_path, "r", encoding="utf-8") as fh:
        transcript = json.load(fh)
    fid = transcript["file_id"]
    meta = _meta_from_transcript(transcript)

    acap = ACAPELLA_DIR / f"{fid}.wav"
    if not acap.exists():
        raise FileNotFoundError(f"missing cached acapella for redo: {acap}")
    import soundfile as sf
    audio, sr = sf.read(str(acap), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1).astype(np.float32)
    if sr != 16000:
        import librosa
        audio = librosa.resample(audio, orig_sr=sr, target_sr=16000).astype(np.float32)

    cluster_emb = {k: np.array(v, dtype=np.float32)
                   for k, v in (transcript.get("cluster_embeddings") or {}).items()}
    segments = transcript.get("segments") or []

    identified, label_to_person = st3.identify_speakers(
        segments, cluster_emb, audio, 16000, meta,
    )
    annotated = st3.annotate_regions(identified, audio, 16000)
    spoken, sung = st3.split_sung_and_spoken(annotated)
    sung = st3.handle_sung_segments(sung, audio, 16000, label_to_person)
    spoken = st3.reattribute_spoken_words(spoken, audio, 16000, label_to_person)
    verified = st3.run_verification(
        spoken, cluster_emb, label_to_person, audio, 16000,
    )
    polished = st3.polish(verified, meta.language)
    polished = sorted(list(polished) + list(sung), key=lambda s: float(s.get("start", 0.0)))
    st3.update_voice_libraries(polished, label_to_person, audio, 16000, meta, is_redo=True)

    transcript["segments"] = polished
    transcript["participants"] = [
        {"id": p.id, "name": _display(p), "role": _role_for(p, meta)}
        for p in label_to_person.values()
    ]
    st3.stamp_db_state(transcript)
    st3.finalize(transcript, polished_path)


def _meta_from_transcript(transcript: dict):
    from filename_parser import SessionMeta
    teacher_id = student_id = None
    for p in transcript.get("participants") or []:
        if p.get("role") == "teacher":
            teacher_id = p["id"]
        elif p.get("role") == "student":
            student_id = p["id"]
    return SessionMeta(
        date=transcript["date"],
        language=transcript["language"],
        teacher_id=teacher_id or "",
        student_id=student_id or "",
        source_path=Path(),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Verbatim ASR pipeline orchestrator.")
    p.add_argument("--redo", action="store_true",
                   help="Reprocess already-polished transcripts with the current voiceprint DB.")
    p.add_argument("--threshold", type=int, default=REDO_THRESHOLD_SESSIONS,
                   help=f"[--redo] min session gain to qualify (default {REDO_THRESHOLD_SESSIONS})")
    p.add_argument("--student", default=None, help="[--redo] only files with this student id")
    p.add_argument("--teacher", default=None, help="[--redo] only files with this teacher id")
    p.add_argument("--confidence-below", type=float, default=None,
                   help="[--redo] only files with any segment below this confidence")
    p.add_argument("--after", default=None,
                   help="[--redo] only files processed_at before this ISO date")
    p.add_argument("--all", action="store_true", help="[--redo] redo everything")
    p.add_argument("--dry-run", action="store_true",
                   help="[--redo] list candidates, don't actually run")
    p.add_argument("--skip-disk-check", action="store_true",
                   help="Bypass the 400 GB free-disk preflight (use only for small test runs)")
    return p


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(
        LOG_DIR / f"run-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}.log",
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s"))
    logging.getLogger().addHandler(fh)

    args = build_arg_parser().parse_args()
    if args.redo:
        rc = asyncio.run(orchestrate_redo(args))
    else:
        rc = asyncio.run(orchestrate_normal(skip_disk_check=args.skip_disk_check))
    sys.exit(rc)


if __name__ == "__main__":
    main()
