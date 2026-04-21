"""
Stage 2 — faster-whisper ASR + WhisperX alignment + pyannote diarization.

GPU work is serialized by the orchestrator via asyncio.Semaphore(1) — this
module does NOT attempt its own concurrency control. All framework imports
are deferred inside functions so the module itself imports cleanly when
torch / whisperx / pyannote are absent (useful for Gate 3 scaffolding and
unit tests of adjacent modules).

Pascal-specific: faster-whisper runs compute_type="int8_float32" (DP4A
native on 1080 Ti). The brief forbids FP16 / int8_float16 on this hardware
and config.py does not expose those — any caller overriding them is acting
against hardware reality.

Phase 5 uses faster-whisper directly (not whisperx.load_model) so we can
pass a per-file `initial_prompt` at transcribe time rather than baking it
into the model load. WhisperX is still used for Phase 6 alignment and
Phase 7 diarization wrap.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config import (
    ALIGN_MODELS,
    CONDITION_ON_PREVIOUS_TEXT,
    DECODE_SAMPLE_RATE,
    DIARIZATION_MODEL,
    HF_TOKEN,
    INITIAL_PROMPTS,
    MAX_SPEAKERS,
    MIN_SPEAKERS,
    WHISPER_BATCH_SIZE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_MODEL,
)

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)

_whisper_pipeline = None        # faster_whisper.BatchedInferencePipeline
_align_cache: dict[str, tuple[Any, Any]] = {}
_diarizer = None                # whisperx.DiarizationPipeline


# ---------------------------------------------------------------------------
# Phase 5 — ASR (faster-whisper, batched)
# ---------------------------------------------------------------------------

def _register_cuda_dll_paths() -> None:
    """
    Windows: CTranslate2 4.x is built against CUDA 12 runtime + cuDNN 8, but
    ships no DLLs itself. Torch's cu118 wheels provide CUDA 11, which doesn't
    satisfy CTranslate2. We install the needed CUDA 12 runtime components via
    pip (`nvidia-cublas-cu12`, `nvidia-cuda-runtime-cu12`, `nvidia-cudnn-cu11`
    — the last one still ships the cuDNN 8 DLLs CTranslate2 expects) and
    register their bin directories here.

    `os.add_dll_directory` alone is NOT sufficient — CTranslate2's C++ loader
    doesn't walk add_dll_directory entries for transitive deps. Belt-and-braces:
      1. add_dll_directory (for direct LoadLibrary calls)
      2. prepend to PATH env var (for any LoadLibrary that respects PATH)
      3. explicit ctypes.CDLL preload (pulls the DLLs into the process so
         later LoadLibraryA resolves them by name already-loaded)
    """
    import ctypes
    import os
    import sys
    if sys.platform != "win32":
        return

    # (package_name, subdir, preload_order). First-hit-wins on name collisions.
    wanted: list[tuple[str, str, tuple[str, ...]]] = [
        ("nvidia.cuda_runtime", "bin", ("cudart64_12.dll",)),
        ("nvidia.cublas",       "bin", ("cublas64_12.dll", "cublasLt64_12.dll")),
        ("nvidia.cudnn",        "bin", (
            "cudnn64_8.dll",
            "cudnn_ops_infer64_8.dll",
            "cudnn_ops_train64_8.dll",
            "cudnn_cnn_infer64_8.dll",
            "cudnn_cnn_train64_8.dll",
            "cudnn_adv_infer64_8.dll",
            "cudnn_adv_train64_8.dll",
        )),
    ]
    total_preloaded = 0
    for mod_name, subdir, preload_order in wanted:
        try:
            mod = __import__(mod_name, fromlist=["__path__"])
        except ImportError:
            log.warning("missing runtime: %s - install via pip", mod_name)
            continue
        # nvidia.* sub-packages are namespace packages: __file__ is None,
        # __path__ holds the directory.
        mod_path = getattr(mod, "__file__", None)
        if mod_path is None:
            paths = list(getattr(mod, "__path__", []))
            if not paths:
                log.warning("%s has neither __file__ nor __path__", mod_name)
                continue
            mod_path = paths[0]
            bin_dir = Path(mod_path) / subdir
        else:
            bin_dir = Path(mod_path).parent / subdir
        if not bin_dir.is_dir():
            log.warning("%s expected at %s but not found", mod_name, bin_dir)
            continue
        os.add_dll_directory(str(bin_dir))
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
        for dll_name in preload_order:
            p = bin_dir / dll_name
            if not p.exists():
                continue
            try:
                ctypes.CDLL(str(p))
                total_preloaded += 1
            except OSError as exc:
                log.warning("ctypes preload failed for %s: %s", dll_name, exc)
    log.info("registered CUDA/cuDNN/cuBLAS (%d DLLs preloaded)", total_preloaded)


# Backwards-compat alias — keep existing callers wired.
_register_cudnn_dll_path = _register_cuda_dll_paths


def load_whisper():
    """Lazy-instantiate the faster-whisper batched pipeline. Singleton."""
    global _whisper_pipeline
    if _whisper_pipeline is not None:
        return _whisper_pipeline
    _register_cuda_dll_paths()
    from faster_whisper import BatchedInferencePipeline, WhisperModel

    model = WhisperModel(
        WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
    )
    _whisper_pipeline = BatchedInferencePipeline(model=model)
    log.info(
        "loaded faster-whisper %s on %s (compute_type=%s)",
        WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
    )
    return _whisper_pipeline


def transcribe(
    audio: "np.ndarray",
    language: str,
    vad_timestamps: list[dict] | None = None,
) -> dict:
    """
    Run ASR with a hard-locked language + per-language initial_prompt.

    `vad_timestamps` is the silero output — list of {start, end} seconds.
    When supplied, faster-whisper only decodes inside those spans. When None,
    whisper handles the full audio (silero pre-filter is strongly preferred
    but not mandatory at this layer).
    """
    pipe = load_whisper()
    prompt = INITIAL_PROMPTS.get(language, "")
    # faster-whisper 1.1.x expects clip_timestamps as a list of dicts with
    # `start` / `end` keys carrying SAMPLE indices (ints), not seconds. Silero
    # returns seconds when return_seconds=True, so convert at the boundary.
    clip_spans = (
        [
            {"start": int(s["start"] * DECODE_SAMPLE_RATE),
             "end":   int(s["end"]   * DECODE_SAMPLE_RATE)}
            for s in vad_timestamps
        ]
        if vad_timestamps
        else None
    )
    segments_iter, info = pipe.transcribe(
        audio,
        language=language,
        batch_size=WHISPER_BATCH_SIZE,
        initial_prompt=prompt,
        condition_on_previous_text=CONDITION_ON_PREVIOUS_TEXT,
        word_timestamps=False,   # alignment happens in Phase 6 via wav2vec2
        clip_timestamps=clip_spans,
    )
    segments = []
    for s in segments_iter:
        segments.append({
            "start": float(s.start),
            "end": float(s.end),
            "text": s.text.strip(),
            "avg_logprob": float(s.avg_logprob) if s.avg_logprob is not None else None,
            "no_speech_prob": float(s.no_speech_prob) if s.no_speech_prob is not None else None,
        })
    log.info("whisper produced %d segments for language=%s", len(segments), language)
    return {"segments": segments, "language": info.language}


# ---------------------------------------------------------------------------
# Phase 6 — WhisperX forced alignment (wav2vec2)
# ---------------------------------------------------------------------------

def load_aligner(language: str):
    """Cache one wav2vec2 aligner per language."""
    if language in _align_cache:
        return _align_cache[language]
    import whisperx

    model_name = ALIGN_MODELS.get(language)
    model, metadata = whisperx.load_align_model(
        language_code=language,
        device=WHISPER_DEVICE,
        model_name=model_name,
    )
    _align_cache[language] = (model, metadata)
    log.info("loaded aligner for %s (model=%s)", language, model_name)
    return model, metadata


def align(
    audio: "np.ndarray",
    segments: list[dict],
    language: str,
) -> list[dict]:
    """
    Attach word-level timestamps via forced alignment.

    Returns the segment list with an added `words_wav2vec2` field per segment
    (list of {word, start, end, score}).
    """
    import whisperx

    if not segments:
        return []
    model, metadata = load_aligner(language)
    aligned = whisperx.align(
        segments,
        model,
        metadata,
        audio,
        WHISPER_DEVICE,
        return_char_alignments=False,
    )
    out: list[dict] = []
    for seg in aligned["segments"]:
        words = [
            {
                "word": w.get("word", "").strip(),
                "start": float(w["start"]) if "start" in w else None,
                "end": float(w["end"]) if "end" in w else None,
                "score": float(w.get("score", 0.0)),
            }
            for w in seg.get("words", [])
            if "start" in w and "end" in w
        ]
        out.append({
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "text": seg.get("text", "").strip(),
            "avg_logprob": seg.get("avg_logprob"),
            "words_wav2vec2": words,
        })
    return out


# ---------------------------------------------------------------------------
# Phase 7 — pyannote diarization (wrapped by WhisperX)
# ---------------------------------------------------------------------------

def _patch_hf_hub_use_auth_token() -> None:
    """Deprecated module-local alias; forwards to utils.hf_compat."""
    from utils.hf_compat import patch_hf_hub_use_auth_token as _p
    _p()


def load_diarizer():
    """
    Lazy-instantiate the pyannote 3.1 speaker-diarization pipeline directly.

    We skip `whisperx.diarize.DiarizationPipeline` because it uses the old
    `use_auth_token=` kwarg. pyannote.audio 3.3.2 still uses that kwarg in
    its own API, so we pass it as-is and let the hf_hub shim translate
    downstream.
    """
    global _diarizer
    if _diarizer is not None:
        return _diarizer
    if not HF_TOKEN:
        raise RuntimeError(
            "HUGGINGFACE_TOKEN / HF_TOKEN must be set for pyannote diarization"
        )
    _patch_hf_hub_use_auth_token()
    import torch
    from pyannote.audio import Pipeline

    _diarizer = Pipeline.from_pretrained(DIARIZATION_MODEL, use_auth_token=HF_TOKEN)
    if torch.cuda.is_available() and WHISPER_DEVICE == "cuda":
        _diarizer.to(torch.device("cuda"))
    log.info("loaded diarizer %s on %s", DIARIZATION_MODEL, WHISPER_DEVICE)
    return _diarizer


def diarize(audio: "np.ndarray"):
    """
    Run diarization hard-clamped to 2 speakers. Returns a pandas DataFrame
    with columns {start, end, speaker} — the shape `assign_word_speakers`
    expects. We build it from pyannote's Annotation output.
    """
    import pandas as pd
    import torch

    pipeline = load_diarizer()
    audio_dict = {
        "waveform": torch.from_numpy(audio).float().unsqueeze(0),
        "sample_rate": 16_000,
    }
    annotation = pipeline(
        audio_dict,
        min_speakers=MIN_SPEAKERS,
        max_speakers=MAX_SPEAKERS,
    )
    rows = [
        {"start": float(segment.start),
         "end":   float(segment.end),
         "speaker": str(speaker)}
        for segment, _, speaker in annotation.itertracks(yield_label=True)
    ]
    return pd.DataFrame(rows, columns=["start", "end", "speaker"])


def attach_speaker_labels(segments: list[dict], diarize_segments) -> list[dict]:
    """
    Overlay pyannote cluster labels onto aligned segments at the word and
    segment level. Adds `speaker` (cluster label like 'SPEAKER_00') to each
    segment and each of its words_wav2vec2 entries. This is the PRE-person-ID
    state — stage3 maps cluster labels onto real person ids.
    """
    import whisperx

    result = {"segments": [
        {
            "start": s["start"],
            "end": s["end"],
            "text": s.get("text", ""),
            "words": s.get("words_wav2vec2", []),
        }
        for s in segments
    ]}
    labeled = whisperx.assign_word_speakers(diarize_segments, result)
    out: list[dict] = []
    for orig, lab in zip(segments, labeled["segments"]):
        new = dict(orig)
        new["cluster_label"] = lab.get("speaker")
        new["words_wav2vec2"] = [
            {
                "word": w.get("word", ""),
                "start": w.get("start"),
                "end": w.get("end"),
                "score": w.get("score", 0.0),
                "cluster_label": w.get("speaker"),
            }
            for w in lab.get("words", [])
        ]
        out.append(new)
    return out


# ---------------------------------------------------------------------------
# Cluster-level embedding extraction (consumed by stage3 matching)
# ---------------------------------------------------------------------------

def cluster_embeddings_from_segments(
    segments: list[dict],
    audio: "np.ndarray",
    sr: int = DECODE_SAMPLE_RATE,
) -> dict[str, "np.ndarray"]:
    """
    Compute a mean embedding per pyannote cluster by concatenating that
    cluster's longest continuous turns (up to ~30s total per cluster) and
    embedding the result.

    Returns {cluster_label: np.ndarray(512,)} ready for matcher.assign_clusters.
    """
    import numpy as np
    from persons.embedder import embed

    by_cluster: dict[str, list[tuple[float, float]]] = {}
    for seg in segments:
        label = seg.get("cluster_label")
        if not label:
            continue
        by_cluster.setdefault(label, []).append((seg["start"], seg["end"]))

    out: dict[str, np.ndarray] = {}
    for label, spans in by_cluster.items():
        # Longest-first so short noise turns don't dominate.
        spans.sort(key=lambda ab: (ab[1] - ab[0]), reverse=True)
        budget_s = 30.0
        used = 0.0
        pieces: list[np.ndarray] = []
        for start_s, end_s in spans:
            take = min(end_s - start_s, budget_s - used)
            if take <= 0.1:
                continue
            start_i = int(start_s * sr)
            end_i = start_i + int(take * sr)
            end_i = min(end_i, len(audio))
            if end_i - start_i < sr // 2:
                continue
            pieces.append(audio[start_i:end_i])
            used += take
            if used >= budget_s:
                break
        if not pieces:
            log.warning("no usable audio for cluster %s; skipping embedding", label)
            continue
        concat = np.concatenate(pieces).astype(np.float32)
        out[label] = embed(concat)
    return out


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------

def teardown_gpu() -> None:
    """Release all GPU-resident models. Call between files to keep VRAM flat."""
    global _whisper_pipeline, _align_cache, _diarizer
    _whisper_pipeline = None
    _align_cache.clear()
    _diarizer = None
    try:
        import gc
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
