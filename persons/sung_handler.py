"""
sung_handler — Phase 3 sung-region branch.

Sung passages (regionizer.classify_segment(...) returns 'sung_*') are routed
through this module instead of through the standard ASR text + alignment +
polish chain. The output is a `[SUNG: ~Xs]` token plus a cosine-only speaker
attribution against the voice library — no Whisper text, no wav2vec2 word
boundaries, no LLM polish.

Why: Whisper hallucinates lyrics on sustained phonation (the dominant
hallucination class for vocal-lesson audio per the SMAC 2026-04-21 report).
Even when transcription is correct, downstream polish has no audio grounding
to verify a lyric is real, so it can mutate freely. Suppressing the text
output entirely is a fidelity win.

Speaker attribution still matters for the lesson record — the cosine pass
against the universal centroid for each known person uses the embedder
directly (bypassing pyannote diarization, which mis-segments sung regions).

Exposed contract:
    handle_sung(segments, audio, sr, voice_libraries) -> list[dict]

`segments` is a slice of the stage 3 segment list where each entry has
`region` set to a 'sung_*' label. `voice_libraries` is the pre-loaded
{person_id: {centroid_name: ndarray}} dict the orchestrator already builds
for the spoken path.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)


def handle_sung(
    segments: list[dict],
    audio: "np.ndarray",
    sr: int,
    voice_libraries: dict[str, dict[str, "np.ndarray"]],
) -> list[dict]:
    """Replace each sung segment's `text` with a `[SUNG: ~Xs]` marker, drop
    word-level fields, attach a cosine-only speaker attribution.

    `voice_libraries` maps person_id → {centroid_name: ndarray}. Pass the
    output of `matcher.load_voice_library()` for each known participant.

    Returns a NEW list (does not mutate input). Segments with `region`
    not starting with 'sung' pass through unchanged.
    """
    from persons.embedder import embed_turn
    from persons.matcher import best_match_score

    # Flatten libraries to a single {label_with_person_prefix: vector} map for
    # best_match_score to scan. Caller distinguishes by name prefix.
    flat_library: dict[str, "np.ndarray"] = {}
    for person_id, lib in voice_libraries.items():
        for name, vec in lib.items():
            flat_library[f"{person_id}::{name}"] = vec

    out: list[dict] = []
    for seg in segments:
        region = seg.get("region", "")
        if not str(region).startswith("sung"):
            out.append(seg)
            continue

        new_seg = dict(seg)
        duration = float(seg.get("end", 0.0)) - float(seg.get("start", 0.0))
        new_seg["text"] = f"[SUNG: ~{round(duration)}s]"
        new_seg["polished"] = True  # skip polish stage entirely
        new_seg["sung"] = True
        # Drop word-level metadata that no longer makes sense.
        new_seg.pop("words", None)

        # Cosine attribution. If the segment is too short for the embedder's
        # 0.5 s minimum, fall through and inherit the upstream label.
        try:
            emb = embed_turn(audio, float(seg["start"]), float(seg["end"]))
        except (ValueError, KeyError) as exc:
            log.warning(
                "sung segment [%.2fs, %.2fs] failed embedding: %s — keeping upstream label",
                seg.get("start", 0.0),
                seg.get("end", 0.0),
                exc,
            )
            out.append(new_seg)
            continue

        if not flat_library:
            out.append(new_seg)
            continue

        cosine, key = best_match_score(emb, flat_library)
        person_id = key.split("::", 1)[0] if key else None
        new_seg["speaker_id"] = person_id or new_seg.get("speaker_id")
        new_seg["speaker_confidence"] = float(cosine)
        new_seg["matched_region"] = key.split("::", 1)[1] if "::" in key else None
        out.append(new_seg)

    return out
