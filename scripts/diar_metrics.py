"""Diarization metrics for the Phase 1 regression harness.

Provides:
- `wder_decomposed`: word-level diarization error rate split into an ASR
  component (substitutions/deletions/insertions) and an assignment component
  (correctly recognized words with the wrong speaker label). The two are
  additive under a single denominator of reference word count.
- `cpwer`: concatenated-minimum-permutation WER over speaker clusters.
- `speaker_purity`: fraction of predicted-cluster time that maps to its
  dominant reference speaker.
- `der`: thin wrapper over `pyannote.metrics.diarization.DiarizationErrorRate`.
  Imported lazily; `pyannote.metrics` is an optional dep.
- `load_hyp_from_whisper_json`: parse a `.whisper.json` sidecar into the
  word/turn structures the metric functions consume.
- `load_ref_from_json`: parse a `.ref.json` v2 file.

All functions are pure; they don't touch audio.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from itertools import permutations
from pathlib import Path
from typing import Iterable, Sequence


_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _normalize_token(text: str) -> str:
    """Strip case and non-word characters so "Hello," matches "hello"."""
    cleaned = "".join(m.group(0) for m in _WORD_RE.finditer(text.lower()))
    return cleaned


def _tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str
    speaker: str


@dataclass(frozen=True)
class Turn:
    start: float
    end: float
    speaker: str


@dataclass
class HypData:
    words: list[Word]
    turns: list[Turn]
    text: str = ""


@dataclass
class RefData:
    words: list[Word]
    turns: list[Turn]
    reference_text: str = ""
    reference_speakers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WDERResult:
    total: float
    asr_component: float
    assignment_component: float
    n_ref: int
    substitutions: int
    deletions: int
    insertions: int
    correct: int
    speaker_errors: int


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _coerce_word(raw: dict) -> Word:
    text = str(raw.get("word") or raw.get("text") or "").strip()
    return Word(
        start=float(raw.get("start", 0.0)),
        end=float(raw.get("end", 0.0)),
        text=text,
        speaker=str(raw.get("speaker") or "").strip(),
    )


def _derive_turns(words: Sequence[Word]) -> list[Turn]:
    if not words:
        return []
    turns: list[Turn] = []
    run_start = words[0].start
    run_end = words[0].end
    run_speaker = words[0].speaker
    for w in words[1:]:
        if w.speaker == run_speaker:
            run_end = max(run_end, w.end)
        else:
            turns.append(Turn(start=run_start, end=run_end, speaker=run_speaker))
            run_start, run_end, run_speaker = w.start, w.end, w.speaker
    turns.append(Turn(start=run_start, end=run_end, speaker=run_speaker))
    return turns


def load_hyp_from_whisper_json(path: str | Path) -> HypData:
    """Load a `.whisper.json` sidecar.

    Requires `words[]` with speaker-tagged entries. `turns[]` is derived by
    collapsing consecutive same-speaker runs when not already present.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    words = [_coerce_word(w) for w in raw.get("words", [])]
    turns_raw = raw.get("turns") or []
    if turns_raw:
        turns = [
            Turn(start=float(t["start"]), end=float(t["end"]), speaker=str(t["speaker"]))
            for t in turns_raw
        ]
    else:
        turns = _derive_turns(words)
    return HypData(words=words, turns=turns, text=str(raw.get("text") or ""))


def load_ref_from_json(path: str | Path) -> RefData:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    words = [_coerce_word(w) for w in raw.get("words", [])]
    turns_raw = raw.get("turns") or []
    if turns_raw:
        turns = [
            Turn(start=float(t["start"]), end=float(t["end"]), speaker=str(t["speaker"]))
            for t in turns_raw
        ]
    else:
        turns = _derive_turns(words)
    return RefData(
        words=words,
        turns=turns,
        reference_text=str(raw.get("reference_text") or ""),
        reference_speakers=list(raw.get("reference_speakers") or []),
    )


# ---------------------------------------------------------------------------
# WDER (decomposed)
# ---------------------------------------------------------------------------

def _align_words(ref: Sequence[Word], hyp: Sequence[Word]) -> list[tuple[str, Word | None, Word | None]]:
    """Return a Levenshtein alignment path.

    Each entry is `(op, ref_word, hyp_word)` with `op` ∈ {"C", "S", "D", "I"}:
    C=correct, S=substitution, D=deletion (hyp missing a ref word),
    I=insertion (hyp has an extra word). Normalization is lowercase + token-only.
    """
    n, m = len(ref), len(hyp)
    if n == 0 and m == 0:
        return []

    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        cost[i][0] = i
    for j in range(m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        r_tok = _normalize_token(ref[i - 1].text)
        for j in range(1, m + 1):
            h_tok = _normalize_token(hyp[j - 1].text)
            if r_tok == h_tok:
                cost[i][j] = cost[i - 1][j - 1]
            else:
                cost[i][j] = 1 + min(
                    cost[i - 1][j],       # deletion
                    cost[i][j - 1],       # insertion
                    cost[i - 1][j - 1],   # substitution
                )

    path: list[tuple[str, Word | None, Word | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            r_tok = _normalize_token(ref[i - 1].text)
            h_tok = _normalize_token(hyp[j - 1].text)
            if r_tok == h_tok and cost[i][j] == cost[i - 1][j - 1]:
                path.append(("C", ref[i - 1], hyp[j - 1]))
                i -= 1
                j -= 1
                continue
            if cost[i][j] == cost[i - 1][j - 1] + 1:
                path.append(("S", ref[i - 1], hyp[j - 1]))
                i -= 1
                j -= 1
                continue
        if i > 0 and (j == 0 or cost[i][j] == cost[i - 1][j] + 1):
            path.append(("D", ref[i - 1], None))
            i -= 1
            continue
        path.append(("I", None, hyp[j - 1]))
        j -= 1

    path.reverse()
    return path


def _best_speaker_map(alignment: Sequence[tuple[str, Word | None, Word | None]]) -> dict[str, str]:
    """Pick the hyp→ref speaker mapping that maximizes correct assignment.

    Uses brute-force permutation (diarization clusters are small, usually 2-4).
    Ties broken by lexicographic ref-speaker order.
    """
    ref_speakers: set[str] = set()
    hyp_speakers: set[str] = set()
    for op, r, h in alignment:
        if r is not None and r.speaker:
            ref_speakers.add(r.speaker)
        if h is not None and h.speaker:
            hyp_speakers.add(h.speaker)
    if not hyp_speakers:
        return {}

    ref_list = sorted(ref_speakers)
    hyp_list = sorted(hyp_speakers)

    pad = max(0, len(hyp_list) - len(ref_list))
    ref_pool = ref_list + [f"__pad_{k}__" for k in range(pad)]

    best_map: dict[str, str] = {}
    best_score = -1
    for perm in permutations(ref_pool, len(hyp_list)):
        mapping = dict(zip(hyp_list, perm))
        score = 0
        for op, r, h in alignment:
            if op == "C" and h is not None and r is not None and mapping.get(h.speaker) == r.speaker:
                score += 1
        if score > best_score:
            best_score = score
            best_map = mapping
    return best_map


def wder_decomposed(
    ref_words: Sequence[Word],
    hyp_words: Sequence[Word],
    collar: float = 0.25,
) -> WDERResult:
    """Split WDER into ASR and assignment components.

    - `asr_component` = (S + D + I) / N_ref.
    - `assignment_component` = (correctly-aligned words with wrong speaker) / N_ref,
      after optimal hyp→ref speaker-label permutation.
    - `total` = `asr_component` + `assignment_component` (shared denominator).

    The `collar` parameter is accepted for API symmetry with `der()`; the
    current implementation is token-alignment based and ignores it.
    """
    del collar  # reserved for a future time-overlap variant

    alignment = _align_words(ref_words, hyp_words)
    n_ref = len(ref_words)

    subs = sum(1 for op, _, _ in alignment if op == "S")
    dels = sum(1 for op, _, _ in alignment if op == "D")
    ins = sum(1 for op, _, _ in alignment if op == "I")
    correct = sum(1 for op, _, _ in alignment if op == "C")

    if n_ref == 0:
        return WDERResult(0.0, 0.0, 0.0, 0, 0, 0, ins, 0, 0)

    mapping = _best_speaker_map(alignment)
    speaker_errors = 0
    for op, r, h in alignment:
        if op == "C" and r is not None and h is not None:
            if mapping.get(h.speaker, "") != r.speaker:
                speaker_errors += 1

    asr = (subs + dels + ins) / n_ref
    assignment = speaker_errors / n_ref
    total = asr + assignment

    return WDERResult(
        total=total,
        asr_component=asr,
        assignment_component=assignment,
        n_ref=n_ref,
        substitutions=subs,
        deletions=dels,
        insertions=ins,
        correct=correct,
        speaker_errors=speaker_errors,
    )


# ---------------------------------------------------------------------------
# cpWER
# ---------------------------------------------------------------------------

def _group_text_by_speaker(words: Sequence[Word]) -> dict[str, str]:
    buckets: dict[str, list[str]] = {}
    for w in words:
        spk = w.speaker or "__unlabeled__"
        buckets.setdefault(spk, []).append(w.text)
    return {spk: " ".join(parts) for spk, parts in buckets.items()}


def _wer_tokens(ref: str, hyp: str) -> tuple[int, int]:
    """Return `(errors, n_ref_tokens)` for a text pair."""
    r = _tokenize(ref)
    h = _tokenize(hyp)
    if not r and not h:
        return 0, 0
    if not r:
        return len(h), 0

    previous = list(range(len(h) + 1))
    for i, r_tok in enumerate(r, start=1):
        current = [i]
        for j, h_tok in enumerate(h, start=1):
            if r_tok == h_tok:
                current.append(previous[j - 1])
            else:
                current.append(1 + min(previous[j], current[j - 1], previous[j - 1]))
        previous = current
    return previous[-1], len(r)


def cpwer(
    ref_by_speaker: dict[str, str] | Sequence[Word],
    hyp_by_speaker: dict[str, str] | Sequence[Word],
) -> float:
    """Concatenated-minimum-permutation WER.

    Accepts either pre-bucketed `{speaker: text}` dicts or raw word sequences.
    Tries every hyp→ref speaker permutation and returns the minimum WER. For
    unequal speaker counts the missing speaker maps to empty text.
    """
    ref_map = ref_by_speaker if isinstance(ref_by_speaker, dict) else _group_text_by_speaker(ref_by_speaker)
    hyp_map = hyp_by_speaker if isinstance(hyp_by_speaker, dict) else _group_text_by_speaker(hyp_by_speaker)

    ref_spks = sorted(ref_map)
    hyp_spks = sorted(hyp_map)
    if not ref_spks and not hyp_spks:
        return 0.0

    pad = max(0, len(ref_spks) - len(hyp_spks))
    hyp_pool = hyp_spks + [f"__hpad_{k}__" for k in range(pad)]
    pad_ref = max(0, len(hyp_spks) - len(ref_spks))
    ref_pool = ref_spks + [f"__rpad_{k}__" for k in range(pad_ref)]

    best = float("inf")
    for perm in permutations(hyp_pool, len(ref_pool)):
        total_err = 0
        total_n = 0
        for r_spk, h_spk in zip(ref_pool, perm):
            r_text = ref_map.get(r_spk, "")
            h_text = hyp_map.get(h_spk, "")
            err, n = _wer_tokens(r_text, h_text)
            total_err += err
            total_n += n
        if total_n == 0:
            score = 0.0 if total_err == 0 else float("inf")
        else:
            score = total_err / total_n
        if score < best:
            best = score
    return best if best != float("inf") else 0.0


# ---------------------------------------------------------------------------
# Speaker purity
# ---------------------------------------------------------------------------

def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def speaker_purity(ref_turns: Sequence[Turn], hyp_turns: Sequence[Turn]) -> float:
    """Fraction of predicted-cluster time spent on its dominant reference speaker.

    Defined per pyannote convention:
        purity = Σ_c max_r overlap(c, r)  /  Σ_c duration(c)
    where c = hyp cluster, r = ref speaker.
    """
    if not hyp_turns:
        return 0.0
    by_cluster: dict[str, list[Turn]] = {}
    for t in hyp_turns:
        by_cluster.setdefault(t.speaker, []).append(t)

    numerator = 0.0
    denominator = 0.0
    ref_speakers = {t.speaker for t in ref_turns}
    for cluster, turns in by_cluster.items():
        cluster_duration = sum(max(0.0, t.end - t.start) for t in turns)
        denominator += cluster_duration
        best = 0.0
        for ref_spk in ref_speakers:
            overlap_total = 0.0
            for ht in turns:
                for rt in ref_turns:
                    if rt.speaker != ref_spk:
                        continue
                    overlap_total += _overlap(ht.start, ht.end, rt.start, rt.end)
            if overlap_total > best:
                best = overlap_total
        numerator += best

    if denominator == 0.0:
        return 0.0
    return numerator / denominator


# ---------------------------------------------------------------------------
# DER (pyannote.metrics wrapper)
# ---------------------------------------------------------------------------

def der(ref_turns: Sequence[Turn], hyp_turns: Sequence[Turn], collar: float = 0.5) -> float:
    """Diarization Error Rate via `pyannote.metrics`.

    `collar` is bilateral (pyannote convention): `collar=0.5` == ±0.25s around
    each reference boundary. Raises `RuntimeError` if `pyannote.metrics` is
    unavailable — the harness treats it as optional.
    """
    try:
        from pyannote.core import Annotation, Segment
        from pyannote.metrics.diarization import DiarizationErrorRate
    except ImportError as exc:
        raise RuntimeError(
            "pyannote.metrics is required for der(); install it via requirements.txt"
        ) from exc

    def _to_annotation(turns: Sequence[Turn]) -> Annotation:
        ann = Annotation()
        for idx, t in enumerate(turns):
            if t.end <= t.start:
                continue
            ann[Segment(t.start, t.end), idx] = t.speaker
        return ann

    metric = DiarizationErrorRate(collar=collar, skip_overlap=False)
    return float(metric(_to_annotation(ref_turns), _to_annotation(hyp_turns)))


__all__ = [
    "Word",
    "Turn",
    "HypData",
    "RefData",
    "WDERResult",
    "wder_decomposed",
    "cpwer",
    "speaker_purity",
    "der",
    "load_hyp_from_whisper_json",
    "load_ref_from_json",
]
