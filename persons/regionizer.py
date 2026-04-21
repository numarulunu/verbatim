"""
Pitch-based vocal region classifier.

For each continuous audio segment attributed to a person, decide which vocal
region it occupies:

  speaking   — narrow pitch variance in the person's speech F0 band
  sung_low   — musical pitch, median in the person's low band
  sung_mid   — mid band
  sung_high  — high band
  sung_full  — pitch held stable for >SUSTAIN_MIN_SECONDS (demonstration)

Bands are PERSON-RELATIVE. A bass's "high" is not a soprano's "high". When a
person has no observed pitch distribution yet, the voice-type default is
used. Once pitch data accumulates, the classifier walks up from
`pitch_range_hz` rather than the static heuristic.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config import PITCH_EXTRACTOR, PYWORLD_FRAME_PERIOD_MS, SUSTAIN_MIN_SECONDS
from persons.schema import PersonRecord

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)

# Heuristic Hz bands per voice-type when no observed data exists.
# Values are approximate boundaries between consecutive regions. Overlap is
# acceptable — the classifier picks the interval the median pitch falls into.
_DEFAULT_BANDS: dict[str, dict[str, tuple[float, float]]] = {
    "bass":      {"speaking": ( 85, 180), "sung_low": ( 75, 175), "sung_mid": (175, 275), "sung_high": (275, 420), "sung_full": ( 75, 420)},
    "baritone":  {"speaking": (100, 200), "sung_low": ( 90, 200), "sung_mid": (200, 330), "sung_high": (330, 500), "sung_full": ( 90, 500)},
    "tenor":     {"speaking": (120, 220), "sung_low": (110, 240), "sung_mid": (240, 420), "sung_high": (420, 700), "sung_full": (110, 700)},
    "alto":      {"speaking": (170, 300), "sung_low": (160, 300), "sung_mid": (300, 500), "sung_high": (500, 780), "sung_full": (160, 780)},
    "mezzo":     {"speaking": (190, 340), "sung_low": (180, 350), "sung_mid": (350, 580), "sung_high": (580, 900), "sung_full": (180, 900)},
    "soprano":   {"speaking": (210, 400), "sung_low": (200, 400), "sung_mid": (400, 700), "sung_high": (700, 1100), "sung_full": (200, 1100)},
    # Fallback when voice_type is unknown — covers a mid-register window.
    "_default":  {"speaking": (100, 280), "sung_low": ( 90, 280), "sung_mid": (280, 500), "sung_high": (500, 900), "sung_full": ( 90, 900)},
}

# A segment whose pitch coefficient-of-variation is below this threshold
# is considered "narrow-pitch" — speaking-like. Sung material typically
# varies musically and exceeds this.
_SPEAKING_PITCH_COV = 0.08


def extract_pitch(audio: "np.ndarray", sr: int) -> "np.ndarray":
    """
    Return F0 contour in Hz. Zero-valued frames indicate unvoiced / no-pitch.

    Uses pyworld's DIO+StoneMask when PITCH_EXTRACTOR='pyworld' (more stable
    for singing), or librosa.pyin as the fallback.
    """
    import numpy as np

    if PITCH_EXTRACTOR == "pyworld":
        try:
            import pyworld
            audio_f64 = audio.astype(np.float64, copy=False)
            f0, t = pyworld.dio(audio_f64, sr, frame_period=PYWORLD_FRAME_PERIOD_MS)  # coarse
            f0 = pyworld.stonemask(audio_f64, f0, t, sr)            # refine
            return f0.astype(np.float32)
        except ImportError:
            log.warning("pyworld not installed; falling back to librosa.pyin")

    import librosa
    f0, _, _ = librosa.pyin(
        audio,
        fmin=librosa.note_to_hz("C2"),   # ~65 Hz
        fmax=librosa.note_to_hz("C7"),   # ~2093 Hz
        sr=sr,
        frame_length=2048,
        hop_length=512,
    )
    return np.nan_to_num(f0, nan=0.0).astype(np.float32)


def default_bands_for_voice_type(
    voice_type: str | None,
) -> dict[str, tuple[float, float]]:
    """Static Hz bands for a voice type. Used until the person has observed pitch data."""
    return dict(_DEFAULT_BANDS.get((voice_type or "").lower(), _DEFAULT_BANDS["_default"]))


def _person_bands(person: PersonRecord | None) -> dict[str, tuple[float, float]]:
    """
    Resolve per-person bands.

    If the person has an observed pitch_range_hz, stratify that into 4
    quartiles for sung_low..sung_high and put speaking at the lowest 30%.
    Otherwise fall back to the voice-type default.
    """
    if person is None or person.pitch_range_hz is None:
        vt = person.voice_type if person else None
        return default_bands_for_voice_type(vt)

    lo, hi = person.pitch_range_hz
    if hi <= lo:
        return default_bands_for_voice_type(person.voice_type)
    q1 = lo + 0.25 * (hi - lo)
    q2 = lo + 0.50 * (hi - lo)
    q3 = lo + 0.75 * (hi - lo)
    speech_hi = lo + 0.35 * (hi - lo)   # speaking covers the lowest ~third
    return {
        "speaking":  (lo, speech_hi),
        "sung_low":  (lo, q2),
        "sung_mid":  (q2, q3),
        "sung_high": (q3, hi),
        "sung_full": (lo, hi),
    }


def classify_segment(
    audio: "np.ndarray",
    sr: int,
    person: PersonRecord | None,
) -> str:
    """
    Classify one continuous segment into one of REGION_LABELS.

    Step 1: extract F0, keep voiced frames only.
    Step 2: if median pitch stays within the person's speaking band AND
            variance is low, label as 'speaking'.
    Step 3: if a single pitch is held stable for >SUSTAIN_MIN_SECONDS, label
            as 'sung_full' (demonstration regions).
    Step 4: otherwise assign sung_low/mid/high by median pitch's band.
    """
    import numpy as np

    f0 = extract_pitch(audio, sr)
    voiced = f0[f0 > 0]
    if voiced.size == 0:
        return "speaking"   # silence-ish -> treat as speech, cheapest default

    median = float(np.median(voiced))
    mean = float(np.mean(voiced))
    cov = float(np.std(voiced) / (mean + 1e-9))
    bands = _person_bands(person)

    sp_lo, sp_hi = bands["speaking"]
    if sp_lo <= median <= sp_hi and cov <= _SPEAKING_PITCH_COV:
        return "speaking"

    # Sustained-pitch detection. Frame period depends on the extractor:
    # pyworld uses a fixed 10ms period (regionizer.extract_pitch sets
    # frame_period=10.0); librosa.pyin uses hop_length/sr.
    if PITCH_EXTRACTOR == "pyworld":
        frame_s = PYWORLD_FRAME_PERIOD_MS / 1000.0
    elif PITCH_EXTRACTOR == "librosa":
        frame_s = 512.0 / sr
    else:
        raise ValueError(
            f"Unknown PITCH_EXTRACTOR {PITCH_EXTRACTOR!r}; "
            "classify_segment's sustained-pitch math has no frame_s for this extractor"
        )
    if _has_sustained_pitch(f0, frame_s, SUSTAIN_MIN_SECONDS):
        return "sung_full"

    for label in ("sung_low", "sung_mid", "sung_high"):
        lo, hi = bands[label]
        if lo <= median < hi:
            return label

    # Median above the high band -> clamp to sung_high.
    return "sung_high"


def segment_by_region(
    audio: "np.ndarray",
    sr: int,
    person: PersonRecord | None,
    window_s: float = 1.5,
    hop_s: float = 0.5,
) -> dict[str, list[tuple[float, float]]]:
    """
    Slide a window over `audio`, classify each chunk, and collapse contiguous
    same-label chunks. Returns {region: [(start_s, end_s), ...]}.
    """
    win = int(window_s * sr)
    hop = int(hop_s * sr)
    if win <= 0 or hop <= 0:
        raise ValueError("window_s and hop_s must be positive")

    results: list[tuple[float, float, str]] = []
    for start in range(0, max(1, len(audio) - win + 1), hop):
        end = start + win
        label = classify_segment(audio[start:end], sr, person)
        results.append((start / sr, end / sr, label))

    if not results:
        return {}

    # Collapse contiguous same-label runs.
    collapsed: dict[str, list[tuple[float, float]]] = {}
    cur_label = results[0][2]
    cur_start = results[0][0]
    cur_end = results[0][1]
    for start_s, end_s, label in results[1:]:
        if label == cur_label and start_s <= cur_end:
            cur_end = max(cur_end, end_s)
        else:
            collapsed.setdefault(cur_label, []).append((cur_start, cur_end))
            cur_label, cur_start, cur_end = label, start_s, end_s
    collapsed.setdefault(cur_label, []).append((cur_start, cur_end))
    return collapsed


def update_pitch_range(person: PersonRecord, f0_hz: "np.ndarray") -> None:
    """Expand `person.pitch_range_hz` using the 5th/95th percentile of voiced f0."""
    import numpy as np
    voiced = f0_hz[f0_hz > 0]
    if voiced.size < 100:
        return
    lo = float(np.percentile(voiced, 5))
    hi = float(np.percentile(voiced, 95))
    if person.pitch_range_hz is None:
        person.pitch_range_hz = (lo, hi)
    else:
        old_lo, old_hi = person.pitch_range_hz
        person.pitch_range_hz = (min(old_lo, lo), max(old_hi, hi))


def _has_sustained_pitch(
    f0: "np.ndarray",
    frame_s: float,
    min_duration_s: float,
    stability_semitones: float = 0.5,
) -> bool:
    """True iff any run of voiced frames stays within `stability_semitones` for >min_duration_s."""
    import numpy as np
    if f0.size == 0 or frame_s <= 0:
        return False
    min_frames = int(min_duration_s / frame_s)
    if min_frames <= 0:
        return False

    run_len = 0
    run_base_hz = 0.0
    for val in f0:
        if val <= 0:
            run_len = 0
            continue
        if run_len == 0:
            run_base_hz = float(val)
            run_len = 1
            continue
        # Semitone distance from run baseline.
        semis = 12.0 * abs(np.log2(val / run_base_hz))
        if semis <= stability_semitones:
            run_len += 1
            if run_len >= min_frames:
                return True
        else:
            run_base_hz = float(val)
            run_len = 1
    return False
