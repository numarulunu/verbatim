"""
word_reattribute — Phase 3 word-level speaker re-attribution.

After Whisper produces word-timestamped output, this module sweeps each
word's audio window past both speaker centroids and flips the label when
the cosine margin exceeds a threshold (config.VERIFICATION_REASSIGN_MARGIN
= 0.15 by default). This catches the teacher/student bleed at fast turn
boundaries that segment-level pyannote diarization systematically misses.

Sung segments are skipped — sustained vowels have stable F0 but provide
poor speaker discrimination at sub-second granularity.

The function never re-decodes Whisper text; only the `speaker_id` /
`speaker_role` / `speaker_confidence` fields per segment may change, plus
a new `reattributed: bool` flag if any word in the segment flipped.

Exposed contract:
    reattribute_words(segments, audio, sr, voice_libraries, margin) -> list[dict]
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config import VERIFICATION_REASSIGN_MARGIN

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)

# Words shorter than this many seconds get their window padded equally on
# both sides so the embedder gets at least 0.5 s of audio (its minimum).
_MIN_WINDOW_S = 0.5


def _word_window(word: dict, audio_dur_s: float) -> tuple[float, float]:
    start = float(word.get("start", 0.0))
    end = float(word.get("end", start))
    duration = max(end - start, 0.0)
    if duration >= _MIN_WINDOW_S:
        return start, end
    pad = (_MIN_WINDOW_S - duration) / 2.0
    new_start = max(0.0, start - pad)
    new_end = min(audio_dur_s, end + pad)
    return new_start, new_end


def reattribute_words(
    segments: list[dict],
    audio: "np.ndarray",
    sr: int,
    voice_libraries: dict[str, dict[str, "np.ndarray"]],
    margin: float = VERIFICATION_REASSIGN_MARGIN,
) -> list[dict]:
    """Per-word speaker re-attribution. Returns a new segment list.

    Mutation contract:
        - Spoken segments may gain `reattributed: True` if any word flipped.
        - Sung segments pass through unchanged.
        - Segments without a `words` field pass through (no Phase 2 metadata).
        - Segments where a fraction > 0.5 of words flipped to a different
          speaker are tagged with the new majority speaker; otherwise the
          per-word flips are recorded but the segment-level label is preserved.
    """
    if not voice_libraries or len(voice_libraries) < 2:
        return segments  # need at least two centroids to compare

    from persons.embedder import embed
    from persons.matcher import _cosine  # type: ignore[attr-defined]

    audio_dur_s = float(len(audio)) / float(sr)
    person_ids = sorted(voice_libraries.keys())

    out: list[dict] = []
    for seg in segments:
        if seg.get("sung") or str(seg.get("region", "")).startswith("sung"):
            out.append(seg)
            continue
        words = seg.get("words")
        if not words:
            out.append(seg)
            continue
        seg_speaker = seg.get("speaker_id")
        if seg_speaker is None:
            out.append(seg)
            continue

        flipped_count = 0
        per_person_votes: dict[str, int] = {p: 0 for p in person_ids}
        for word in words:
            start, end = _word_window(word, audio_dur_s)
            window = audio[int(start * sr):int(end * sr)]
            if window.size < sr // 2:
                continue
            try:
                emb = embed(window)
            except (ValueError, RuntimeError) as exc:
                log.debug("word embed failed [%.2f, %.2f]: %s", start, end, exc)
                continue

            best_pid = seg_speaker
            best_score = -1.0
            for pid in person_ids:
                lib = voice_libraries[pid]
                for centroid in lib.values():
                    if centroid.ndim == 1:
                        score = _cosine(emb, centroid)
                        if score > best_score:
                            best_score, best_pid = score, pid
                    elif centroid.ndim == 2:
                        for row in centroid:
                            score = _cosine(emb, row)
                            if score > best_score:
                                best_score, best_pid = score, pid
            per_person_votes[best_pid] = per_person_votes.get(best_pid, 0) + 1
            if best_pid != seg_speaker and best_score - seg.get("speaker_confidence", 0.0) > margin:
                flipped_count += 1
                word["reattributed"] = True
                word["reattributed_to"] = best_pid

        new_seg = dict(seg)
        if flipped_count > 0:
            new_seg["reattributed"] = True
            # Majority-flip: if > half of words went to a single OTHER speaker,
            # promote that to the segment-level label.
            non_self = {p: c for p, c in per_person_votes.items() if p != seg_speaker}
            if non_self:
                top_pid, top_count = max(non_self.items(), key=lambda kv: kv[1])
                if top_count > len(words) / 2:
                    new_seg["speaker_id"] = top_pid
                    new_seg["reattributed_segment_flip"] = True
        out.append(new_seg)

    return out
