# Montreal Forced Aligner — setup

MFA is **optional**. The main pipeline runs without it; word timestamps come
from wav2vec2 forced alignment in Stage 6. MFA produces phoneme-level
alignment useful for downstream vocal pedagogy research.

## Why a separate env

MFA's dependencies (Kaldi, specific Python versions) conflict with the
faster-whisper / pyannote stack in the main env. Keep it isolated.

## Install

```bash
conda create -n mfa -c conda-forge montreal-forced-aligner
conda activate mfa
mfa model download acoustic english_us_arpa
mfa model download dictionary english_us_arpa
mfa model download acoustic romanian_ro
mfa model download dictionary romanian_ro
```

## Run

From the Vocality root, with the `mfa` env active:

```bash
python mfa_align.py 2024-03-15_ionut__madalina_en
python mfa_align.py --student madalina_r
python mfa_align.py --verify
```

## Validation

`mfa_align.py` computes word-overlap between MFA output and the transcript
already in `03_polished/<file_id>.json`. If overlap < 95%, MFA output is
rejected and the existing `words_wav2vec2` is retained.

## Custom dictionary

`mfa_custom_dict.yaml` ships vocal-pedagogy terminology that would
otherwise be dropped. Extend it as gaps are observed in validation logs.
