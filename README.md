# Verbatim

Local Electron desktop app + Python ASR pipeline for transcribing vocal-lesson
recordings into a named-entity pedagogical research corpus. Every utterance is
attributed to a real person whose voiceprint, voice type, and session history
are stored in one coherent database that sharpens with every run.

The Electron shell (`verbatim/`) is the user surface. It spawns the Python
daemon (`engine_daemon.py` in dev, `verbatim-engine.exe` in packaged builds)
and brokers all interaction over JSON-line IPC. There is no longer a separate
CLI surface — registry / redo / batch are all driven from the renderer.

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
| `VERBATIM_ROOT`        | optional       | Override project root                  |

For `POLISH_ENGINE="cli"`: Claude Code CLI must be installed and logged in.

## Run

```bash
# Dev mode — launches the Electron shell + spawns the Python daemon
cd verbatim
npm install
npm start
```

Participants register from the Registry panel inside the app. Batch
processing, redo, and corpus inspection all live in the renderer UI.

For headless / scripted runs the daemon path is still callable directly:

```bash
.venv/Scripts/python.exe engine_daemon.py < commands.jsonl > events.jsonl
```

The daemon's IPC protocol is documented in `verbatim/ipc-protocol.json`.

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

## Build (Windows installer)

```bash
cd verbatim
npm run build-all-win   # fetch ffmpeg + freeze engine + build installer
```

Output lands in `verbatim/dist/Verbatim-Transcribe-Setup-X.Y.Z.exe`. See
`docs/packaging.md` for the full build / publish flow.
