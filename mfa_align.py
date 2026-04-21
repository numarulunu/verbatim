"""
Optional Montreal Forced Aligner phoneme alignment.

NOT part of the main pipeline. Separate Conda env. On-demand only.
Validates its own output: if <95% word overlap with the existing wav2vec2
transcript, MFA output is rejected and the original words_wav2vec2 is
retained. Otherwise a `words_mfa` field is added to each polished segment.

The default dictionary is MFA's built-in `english_mfa`. Pass `--dictionary`
to override with a custom `.dict` path. `mfa/mfa_custom_dict.yaml` holds
music-terminology phonemes for future use — not wired in by default.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from config import ACAPELLA_DIR, POLISHED_DIR
from utils.atomic_write import atomic_write_json

log = logging.getLogger(__name__)

WORD_OVERLAP_THRESHOLD = 0.95
MFA_TIMEOUT_S = 900  # 15 minutes per file; realistic for 10-60 min audio
DEFAULT_ACOUSTIC_MODEL = "english_mfa"
DEFAULT_DICTIONARY = "english_mfa"  # MFA's built-in English dict; run `mfa model download dictionary english_mfa` once


def align_one(
    file_id: str,
    acoustic_model: str = DEFAULT_ACOUSTIC_MODEL,
    dictionary: str = DEFAULT_DICTIONARY,
) -> bool:
    """
    Align a single polished transcript via MFA. Returns True on success, False
    otherwise (missing inputs, MFA error, timeout, or <95% word overlap).

    On success, writes words_mfa into each segment of the polished JSON and
    sets transcript["mfa_aligned"] = True.
    """
    polished_path = POLISHED_DIR / f"{file_id}.json"
    if not polished_path.exists():
        log.error("no polished transcript for %s at %s", file_id, polished_path)
        return False
    acapella_path = ACAPELLA_DIR / f"{file_id}.wav"
    if not acapella_path.exists():
        log.error("no acapella for %s at %s", file_id, acapella_path)
        return False

    transcript = json.loads(polished_path.read_text(encoding="utf-8"))
    ref_text = " ".join(
        (seg.get("text") or "").strip() for seg in transcript.get("segments", [])
    ).strip()
    if not ref_text:
        log.error("empty transcript text for %s; nothing to align", file_id)
        return False

    if shutil.which("mfa") is None:
        log.error(
            "`mfa` CLI not found on PATH. Activate the MFA conda env first: "
            "`conda activate mfa`. See mfa/mfa_setup.md for setup."
        )
        return False

    with tempfile.TemporaryDirectory(prefix="vocality_mfa_") as tmpdir:
        tmp = Path(tmpdir)
        corpus = tmp / "corpus" / "speaker_01"
        corpus.mkdir(parents=True)
        # Copy (don't symlink — Windows quirks) the acapella into the MFA corpus.
        shutil.copyfile(acapella_path, corpus / f"{file_id}.wav")
        (corpus / f"{file_id}.lab").write_text(ref_text, encoding="utf-8")

        output_dir = tmp / "out"
        cmd = [
            "mfa", "align",
            str(tmp / "corpus"),
            dictionary,
            acoustic_model,
            str(output_dir),
            "--clean",
        ]
        log.info("running: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=MFA_TIMEOUT_S,
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired:
            log.error("mfa align timed out after %ds for %s", MFA_TIMEOUT_S, file_id)
            return False
        if result.returncode != 0:
            log.error("mfa align exited %d for %s: %s",
                      result.returncode, file_id, result.stderr[:600])
            return False

        tg_path = output_dir / "speaker_01" / f"{file_id}.TextGrid"
        if not tg_path.exists():
            log.error("mfa produced no TextGrid at %s", tg_path)
            return False
        words_mfa = _parse_textgrid(tg_path)

    overlap = _compute_overlap(words_mfa, transcript.get("segments", []))
    log.info("mfa word overlap for %s: %.1f%%", file_id, overlap * 100)
    if overlap < WORD_OVERLAP_THRESHOLD:
        log.warning(
            "rejecting mfa output for %s: overlap %.1f%% < %.0f%% threshold "
            "(keeping existing words_wav2vec2)",
            file_id, overlap * 100, WORD_OVERLAP_THRESHOLD * 100,
        )
        return False

    # Merge words_mfa into each segment by time range.
    for seg in transcript.get("segments", []):
        s_start = float(seg.get("start", 0.0))
        s_end = float(seg.get("end", 0.0))
        seg["words_mfa"] = [
            w for w in words_mfa
            if w["start"] >= s_start - 0.001 and w["end"] <= s_end + 0.001
        ]
    transcript["mfa_aligned"] = True
    atomic_write_json(polished_path, transcript)
    log.info("mfa aligned %s (%d words, %.1f%% overlap)",
             file_id, len(words_mfa), overlap * 100)
    return True


def align_many(
    file_ids: list[str],
    acoustic_model: str = DEFAULT_ACOUSTIC_MODEL,
    dictionary: str = DEFAULT_DICTIONARY,
) -> tuple[int, int]:
    """Align multiple files. Returns (ok_count, total)."""
    ok = 0
    for fid in file_ids:
        if align_one(fid, acoustic_model=acoustic_model, dictionary=dictionary):
            ok += 1
    return ok, len(file_ids)


def verify(polished_path: Path) -> float:
    """
    Compute word-overlap ratio between existing words_mfa (if any) and
    words_wav2vec2 in an already-processed polished JSON. Does NOT call mfa.
    Returns ratio in [0, 1]; 0.0 if no words_mfa exists.
    """
    transcript = json.loads(Path(polished_path).read_text(encoding="utf-8"))
    mfa_words: list[dict] = []
    for seg in transcript.get("segments", []):
        mfa_words.extend(seg.get("words_mfa") or [])
    if not mfa_words:
        return 0.0
    return _compute_overlap(mfa_words, transcript.get("segments", []))


def _parse_textgrid(path: Path) -> list[dict]:
    """
    Parse MFA TextGrid output. Expect tiers: 'words' and 'phones'. We only
    extract words here — phones are available in the TextGrid for downstream
    consumers that want to reload them.
    """
    try:
        from praatio import textgrid
    except ImportError as exc:
        raise RuntimeError(
            "praatio is required in the MFA conda env: `pip install praatio`"
        ) from exc

    tg = textgrid.openTextgrid(str(path), includeEmptyIntervals=False)
    # Modern MFA uses lowercase 'words'; some older versions capitalize.
    tier_name = "words" if "words" in tg.tierNames else tg.tierNames[0]
    tier = tg.getTier(tier_name)

    out: list[dict] = []
    for interval in tier.entries:
        label = (interval.label or "").strip()
        if not label:
            continue
        out.append({
            "word": label,
            "start": float(interval.start),
            "end": float(interval.end),
            "score": None,   # MFA doesn't expose per-word confidence
        })
    return out


def _compute_overlap(mfa_words: list[dict], segments: list[dict]) -> float:
    """
    Fraction of MFA words that have a matching wav2vec2 word: same casefolded
    text AND start-time within 100 ms. `segments` must carry `words_wav2vec2`.
    Returns 0.0 if either side is empty.
    """
    if not mfa_words:
        return 0.0
    w2v: list[dict] = []
    for seg in segments:
        w2v.extend(seg.get("words_wav2vec2") or [])
    if not w2v:
        return 0.0
    matched = 0
    for m in mfa_words:
        m_word = m["word"].strip().casefold()
        m_start = m["start"]
        for w in w2v:
            w_word = (w.get("word") or "").strip().casefold()
            w_start = float(w.get("start") or 0.0)
            if w_word == m_word and abs(w_start - m_start) < 0.1:
                matched += 1
                break
    return matched / len(mfa_words)


def _discover_by_student(student_id: str) -> list[str]:
    """Return file_ids in POLISHED_DIR/ that have this student."""
    hits = []
    for polished in sorted(POLISHED_DIR.glob("*.json")):
        try:
            data = json.loads(polished.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for p in data.get("participants") or []:
            if p.get("id") == student_id and p.get("role") == "student":
                hits.append(polished.stem)
                break
    return hits


def _discover_all_polished() -> list[str]:
    if not POLISHED_DIR.exists():
        return []
    return sorted(p.stem for p in POLISHED_DIR.glob("*.json"))


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Optional MFA phoneme alignment. Requires the `mfa` CLI "
                    "on PATH — activate the mfa conda env first."
    )
    p.add_argument("file_id", nargs="?",
                   help="file_id (e.g. 2024-03-15_ionut__madalina_en) or omit when using --student/--verify")
    p.add_argument("--student", help="Align every polished transcript with this student id")
    p.add_argument("--verify", action="store_true",
                   help="Report word-overlap on polished JSONs that already have words_mfa; do not call mfa")
    p.add_argument("--acoustic-model", default=DEFAULT_ACOUSTIC_MODEL,
                   help="MFA acoustic model name (default: english_mfa)")
    p.add_argument("--dictionary", default=DEFAULT_DICTIONARY,
                   help=f"MFA dictionary (name or .dict path; default: {DEFAULT_DICTIONARY})")
    return p


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    args = build_arg_parser().parse_args()

    if args.verify:
        any_reported = False
        for fid in _discover_all_polished():
            polished = POLISHED_DIR / f"{fid}.json"
            ratio = verify(polished)
            if ratio > 0:
                print(f"{fid}: words_mfa overlap {ratio*100:.1f}%")
                any_reported = True
        if not any_reported:
            print("no polished transcripts have words_mfa yet.")
        return

    if args.student:
        fids = _discover_by_student(args.student)
        if not fids:
            log.error("no polished files found for student %r", args.student)
            sys.exit(1)
        ok, total = align_many(fids, acoustic_model=args.acoustic_model,
                                dictionary=args.dictionary)
        log.info("aligned %d / %d", ok, total)
        sys.exit(0 if ok == total else 1)

    if not args.file_id:
        log.error("provide a file_id, --student <id>, or --verify")
        sys.exit(2)
    ok = align_one(args.file_id, acoustic_model=args.acoustic_model,
                    dictionary=args.dictionary)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
