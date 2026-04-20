# Benchmark Pack Labeling Workflow (Phase 1 / v2 manifest)

Target: 10 real Vocality coaching clips, stratified per `manifest_v2.json`. Budget: ~22 min per clip × 10 = ~3.5 h total. Output: one `.ref.json` v2 per clip under `references/`, plus the corresponding `.wav` under `audio/`.

## Required strata (10 slots)

| Stratum | Count | What to pick |
|---|---|---|
| `monologue` | 1 | Single speaker for >30 s. Teacher explaining a concept. |
| `clean_en_2spk` | 2 | Two clear English speakers, low overlap, studio-grade audio. |
| `clean_ro_2spk` | 1 | Two Romanian speakers, clear, low overlap. |
| `code_switch` | 1 | RO/EN switching within the same turn (Vocality's reality). |
| `overlap` | 2 | ≥15% overlap. One English, one RO/EN. |
| `short_turns` | 2 | Rapid back-and-forth, many turns < 1 s. One per language. |
| `singing_mixed` | 1 | Coach-feedback over sung vocalise (hardest for pyannote). |

## Clip selection rules

- Length: 3-8 min per clip. Shorter under-samples; longer blows the labeling budget.
- Source: real Vocality coaching sessions. Anonymize filenames — no student names.
- Remove intros/outros before labeling (keep the coaching content only).
- Normalize to 16 kHz mono WAV (`ffmpeg -i in.mp3 -ar 16000 -ac 1 out.wav`).

## Audacity workflow (per clip)

1. Open the WAV in Audacity.
2. `Tracks → Add New → Label Track` (Ctrl+Shift+L).
3. Play the audio. When a speaker starts, press **Ctrl+B** to create a point label. Type the speaker tag (`S1`, `S2`, …) + space + their spoken phrase. Press Enter.
4. At the next speaker change or at a word boundary, **Ctrl+B** again. New label, new tag/phrase.
5. For overlapping speech, create two parallel label tracks (one per speaker) or inline `S1+S2` tags on a single track — the converter accepts either.
6. When done: `File → Export → Export Labels…` → save as `<clip-id>.labels.txt` (TSV with `start \t end \t label`).
7. Also export a plain transcript: `File → Export → Export Other → Export Labels as Text` won't include word timings cleanly, so instead produce the transcript as a free-text file (`<clip-id>.transcript.txt`) with the same content pasted in turn order. This is optional if the label file already contains per-word phrases.

### Label schema the converter accepts

Each Audacity label's text field carries the spoken phrase, prefixed by the speaker tag:

```
0.420  0.680  S1 salut
0.710  0.950  S2 hello
0.960  2.140  S1 cum te cheamă
```

- Speaker tag = first whitespace-delimited token (`S1`, `S2`, `TEACHER`, `STUDENT`, …).
- Remainder = phrase. Each phrase is tokenized into words by the converter; each word inherits the label's `[start, end]` interval (even split).
- Empty phrase → label acts as a pure turn-boundary (no words emitted).

## Conversion

```bash
python backend/scripts/audacity_to_ref.py \
  --labels  backend/tests/fixtures/benchmark_pack/audio/tune-overlap-001.labels.txt \
  --audio   backend/tests/fixtures/benchmark_pack/audio/tune-overlap-001.wav \
  --id      tune-overlap-001 \
  --stratum overlap \
  --language en \
  --out     backend/tests/fixtures/benchmark_pack/references/tune-overlap-001.ref.json
```

Re-running the converter on the same inputs must produce a byte-identical output file. If it doesn't, that's a determinism bug — file it, don't continue.

## QA checklist before committing a clip

- [ ] `.wav` is 16 kHz mono, duration matches stratum budget (3-8 min).
- [ ] `.labels.txt` has ≥1 label per spoken second on average (no huge silence gaps).
- [ ] Speaker tags are consistent (`S1` is the same person throughout the clip).
- [ ] `.ref.json` v2 validates against `pytest -m benchmark backend/tests/test_benchmark_pack_v2.py`.
- [ ] Spot-check: open `.ref.json`, confirm a known phrase is tagged to the right speaker.

## Why the 22 min/clip budget

~5 min clip × (1x listen + 1x re-listen for label placement + 1x QA pass) = ~15 min core labeling + 7 min tooling/export overhead. If a clip takes >30 min, the audio quality is probably too poor for labeling — defer it and pick another.

## When to expand beyond 10

Phase 1 ships with 10. Per-stratum medians are too noisy to trust until ≥20 clips; the `history.csv` currently logs composite medians only for this reason. If a Phase-2+ experiment touches a single stratum (e.g., overlap-heavy rewrite), add 5 more overlap clips before claiming a delta.
