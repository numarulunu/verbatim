# Montreal Forced Aligner — setup

MFA is **optional**. The main pipeline produces word-level timestamps via wav2vec2 in Stage 6. MFA adds *phoneme*-level alignment useful for vocal-pedagogy research — where each vowel / consonant starts and ends, not just each word.

## Why a separate env

MFA depends on Kaldi. Kaldi conflicts with the faster-whisper / pyannote / silero stack in `.venv/`. Keep MFA in its own Conda env.

## Install (one-time)

```bash
conda create -n mfa -c conda-forge "montreal-forced-aligner>=3.0"
conda activate mfa

# English acoustic model + dictionary (MFA v3 "third party" models).
mfa model download acoustic english_mfa
mfa model download dictionary english_mfa

# TextGrid parser used by mfa_align.py.
pip install praatio
```

For Romanian: `mfa model download acoustic romanian_mfa` + `mfa model download dictionary romanian_mfa` and pass `--acoustic-model romanian_mfa` at invocation time.

## Run

Activate the mfa env, then invoke `mfa_align.py` with the PROJECT's Python (if your mfa env has Python >=3.11, you can just use its python). From the project root:

```bash
conda activate mfa

# Align one file
python mfa_align.py 2024-03-15_ionut__madalina_en

# Align every polished transcript with a given student
python mfa_align.py --student madalina_r

# Report word-overlap on files that already have words_mfa (no realignment)
python mfa_align.py --verify
```

## What it writes

On success, each segment of the polished JSON gains a `words_mfa` array:

```json
{
  "start": 12.34,
  "end": 15.67,
  "text": "Try opening the vowel more on the top note.",
  "words_wav2vec2": [...],
  "words_mfa": [
    {"word": "try", "start": 12.34, "end": 12.58, "score": null},
    {"word": "opening", "start": 12.58, "end": 12.94, "score": null},
    ...
  ]
}
```

Top-level `"mfa_aligned": true` is also set.

## Rejection gate

`mfa_align.py` rejects MFA output whose word overlap with the existing `words_wav2vec2` is below 95%. Rejection leaves the polished JSON untouched (`words_mfa` absent, `mfa_aligned` stays false). This happens when MFA's pronunciation dictionary cannot resolve enough of the transcript — usually music-terminology gaps. Extend `mfa/mfa_custom_dict.yaml` when you observe it.

## Custom dictionary (music terminology)

`mfa/mfa_custom_dict.yaml` holds phoneme spellings for vocal-pedagogy terms MFA's default English dictionary doesn't know (passaggio, appoggio, coloratura, squillo, portamento, chiaroscuro, bel canto, etc). It is currently a **reference document**, not wired into the default alignment flow — `mfa_align.py` uses `english_mfa` as the dictionary by default.

To activate music-terminology support, convert the YAML to MFA's plain-text `.dict` format (one word + space-separated ARPAbet phones per line), merge it with `english_mfa`'s default dictionary, and pass the merged path via `--dictionary`:

```bash
# Locate english_mfa's dictionary file
mfa model inspect dictionary english_mfa

# Create a merged .dict manually (example)
cat ~/Documents/MFA/pretrained_models/dictionary/english_mfa.dict mfa/music_terms.dict > mfa/merged.dict

# Align with the merged dict
python mfa_align.py 2024-03-15_ionut__madalina_en --dictionary mfa/merged.dict
```

MFA will also mark any OOV (out-of-vocabulary) words in its stderr — extend your `.dict` file as you see new terms fail to align.

## Troubleshooting

- `mfa: command not found`: conda env isn't activated. Run `conda activate mfa`.
- `No acoustic model 'english_mfa' found`: run `mfa model download acoustic english_mfa`.
- `praatio` import error: `pip install praatio` inside the mfa env.
- TextGrid parse errors: check MFA's `mfa align` stderr — alignment may have silently produced a malformed output. Re-run with `--verbose` (edit `mfa_align.py` cmd list).
- Timeout (default 15 min per file): bump `MFA_TIMEOUT_S` at the top of `mfa_align.py`. MFA is CPU-bound and scales with audio length.
