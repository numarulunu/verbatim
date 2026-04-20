# Vocality ASR

Local-only Python pipeline for transcribing vocal-lesson recordings into a
named-entity pedagogical research corpus. Every utterance is attributed to
a real person whose voiceprint, voice type, and session history are stored
in one coherent database that sharpens with every run.

## Hardware target (fixed)

- **GPU:** NVIDIA GTX 1080 Ti (Pascal, 11 GB). Uses `int8_float32` (DP4A).
- **CPU:** Intel i7-12700K. Decode workers pinned to P-cores (logicals 0-15).
- **OS:** Windows 11.

## Install

```bash
# 1. Torch CUDA 11.8 wheels (manual step — CUDA-specific)
pip install torch==2.5.1+cu118 torchvision==0.20.1+cu118 torchaudio==2.5.1+cu118 \
    --index-url https://download.pytorch.org/whl/cu118

# 2. Pipeline deps
pip install -r requirements.txt

# 3. FFmpeg on PATH
winget install Gyan.FFmpeg

# 4. HuggingFace — accept terms for these gated models:
#    pyannote/speaker-diarization-3.1
#    pyannote/embedding
#    pyannote/segmentation-3.0
```

## Environment variables

| Variable               | Required       | Purpose                                |
|------------------------|----------------|----------------------------------------|
| `HUGGINGFACE_TOKEN`    | yes            | Pyannote model download                |
| `ANTHROPIC_API_KEY`    | only for `api` | Polish engine (when `POLISH_ENGINE="api"`) |
| `VOCALITY_ROOT`        | optional       | Override project root                  |

For `POLISH_ENGINE="cli"`: Claude Code CLI must be installed and logged in.

## Run

```bash
# Register participants first
python enroll.py register --id ionut    --name "Ionuț"    --default-role teacher --voice-type bass
python enroll.py register --id madalina --name "Mădălina" --default-role student --voice-type soprano

# Normal run — processes everything in Material/ that isn't already polished
python run.py

# Redo — reprocess files where the voiceprint DB has matured meaningfully
python run.py --redo --threshold 3
python run.py --redo --student madalina --dry-run

# Cleanup intermediate files after outputs are verified
python cleanup.py

# Optional MFA phoneme alignment (separate conda env)
python mfa_align.py <file_id>
```

## Filename convention

```
YYYY-MM-DD_<teacher_id>__<student_id>_<lang>.<ext>
```

Examples:

- `2024-03-15_ionut__madalina_en.mp4`
- `2024-05-10_ionut__madalina_r_ro.mp4`

Double underscore (`__`) separates participants; teacher first. Language
must be `en` or `ro`. Legacy single-name form is also accepted — teacher
defaults to `ionut`.

## Data layout

```
Material/               ← your source recordings (read-only)
01_acapella/            ← MelBand Roformer output (Stage 1)
02_raw_json/            ← Whisper + alignment + diarization (Stages 5-7)
03_polished/            ← final transcripts (Stages 8-10)
_voiceprints/           ← per-person voice libraries + metadata
_logs/                  ← pipeline logs
corpus.json             ← session index
session_map.json        ← manual filename overrides (optional)
```

All of the above are gitignored. Voiceprints are biometric data — local only,
no cloud, no commits.

## Tests

```bash
pytest
```

## Status

Scaffold stage. Modules stubbed with `NotImplementedError`. Implementation
lands in Gate 4.
