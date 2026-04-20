"""Convert Audacity label-track TSV into a `.ref.json` v2 file.

Audacity label format (one line per label, tab-separated):

    <start_sec>\t<end_sec>\t<Speaker-tag> <spoken phrase>

The first whitespace-delimited token of the label text is the speaker tag
(`S1`, `S2`, `TEACHER`, …). The remainder is the phrase, tokenized into
words and distributed uniformly across `[start, end]`. Empty phrases emit
a pure turn boundary with no words.

Output schema matches `LABELING.md`:

    {
      "version": 2,
      "id": ...,
      "stratum": ...,
      "language": ...,
      "duration_sec": ...,
      "max_wer": 0.25,
      "reference_text": "word word word ...",
      "reference_speakers": ["S1", "S2"],
      "words": [ {start, end, word, speaker}, ... ],
      "turns": [ {start, end, speaker}, ... ]
    }

Determinism contract: identical inputs → byte-identical output (UTF-8,
`indent=2`, `sort_keys=False`, trailing newline). Verified by `test_diar_metrics.py`
round-trip + `LABELING.md` QA step.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class Label:
    start: float
    end: float
    speaker: str
    phrase: str


def _parse_labels(path: Path) -> list[Label]:
    labels: list[Label] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            raise ValueError(f"{path}:{lineno}: expected 3 tab-separated fields, got {len(parts)}")
        try:
            start = float(parts[0])
            end = float(parts[1])
        except ValueError as exc:
            raise ValueError(f"{path}:{lineno}: non-numeric time column") from exc
        if end < start:
            raise ValueError(f"{path}:{lineno}: end {end} < start {start}")
        text = parts[2].strip()
        if not text:
            # Anonymous boundary — skip.
            continue
        head, _, rest = text.partition(" ")
        speaker = head.strip()
        phrase = rest.strip()
        labels.append(Label(start=start, end=end, speaker=speaker, phrase=phrase))
    labels.sort(key=lambda l: (l.start, l.end))
    return labels


def _tokenize_phrase(phrase: str) -> list[str]:
    return [m.group(0) for m in _WORD_RE.finditer(phrase)]


def _words_from_label(label: Label) -> list[dict]:
    tokens = _tokenize_phrase(label.phrase)
    if not tokens:
        return []
    span = max(label.end - label.start, 0.001)
    step = span / len(tokens)
    out: list[dict] = []
    for idx, tok in enumerate(tokens):
        w_start = label.start + idx * step
        w_end = label.start + (idx + 1) * step if idx < len(tokens) - 1 else label.end
        out.append({
            "start": round(w_start, 3),
            "end": round(w_end, 3),
            "word": tok,
            "speaker": label.speaker,
        })
    return out


def _collapse_turns(labels: Iterable[Label]) -> list[dict]:
    turns: list[dict] = []
    current: dict | None = None
    for lbl in labels:
        if current and current["speaker"] == lbl.speaker and lbl.start <= current["end"] + 1e-6:
            current["end"] = max(current["end"], lbl.end)
            continue
        if current is not None:
            turns.append({
                "start": round(current["start"], 3),
                "end": round(current["end"], 3),
                "speaker": current["speaker"],
            })
        current = {"start": lbl.start, "end": lbl.end, "speaker": lbl.speaker}
    if current is not None:
        turns.append({
            "start": round(current["start"], 3),
            "end": round(current["end"], 3),
            "speaker": current["speaker"],
        })
    return turns


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 16000
            return frames / float(rate)
    except (wave.Error, OSError):
        return 0.0


def build_ref(
    labels_path: Path,
    audio_path: Path | None,
    clip_id: str,
    stratum: str,
    language: str,
    max_wer: float,
) -> dict:
    labels = _parse_labels(labels_path)

    words: list[dict] = []
    for lbl in labels:
        words.extend(_words_from_label(lbl))

    turns = _collapse_turns(labels)
    reference_text = " ".join(w["word"] for w in words)
    reference_speakers = sorted({lbl.speaker for lbl in labels})

    duration = _wav_duration(audio_path) if audio_path and audio_path.exists() else 0.0
    if not duration and labels:
        duration = labels[-1].end

    return {
        "version": 2,
        "id": clip_id,
        "stratum": stratum,
        "language": language,
        "duration_sec": round(duration, 3),
        "max_wer": max_wer,
        "reference_text": reference_text,
        "reference_speakers": reference_speakers,
        "words": words,
        "turns": turns,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audacity labels → .ref.json v2")
    parser.add_argument("--labels", required=True, type=Path, help="Audacity export TSV (start\\tend\\ttext)")
    parser.add_argument("--audio", type=Path, default=None, help="WAV file; used for duration_sec only")
    parser.add_argument("--id", required=True, dest="clip_id", help="e.g. tune-overlap-001")
    parser.add_argument("--stratum", required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--max-wer", type=float, default=0.25)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.labels.exists():
        print(f"labels file missing: {args.labels}", file=sys.stderr)
        return 2

    ref = build_ref(
        labels_path=args.labels,
        audio_path=args.audio,
        clip_id=args.clip_id,
        stratum=args.stratum,
        language=args.language,
        max_wer=args.max_wer,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic output: no sort_keys (preserve schema order), no trailing whitespace.
    payload = json.dumps(ref, ensure_ascii=False, indent=2) + "\n"
    args.out.write_text(payload, encoding="utf-8")
    print(f"wrote {args.out} ({len(ref['words'])} words, {len(ref['turns'])} turns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
