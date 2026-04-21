"""
Verbatim — centralized configuration.

All tunables, paths, and model parameters live here. Stage modules must not
contain magic numbers or hardcoded paths. Secrets are read from environment
variables only.

Hardware target (fixed): NVIDIA GTX 1080 Ti (Pascal SM 6.1, 11 GB, DP4A)
                         Intel i7-12700K (8 P-cores logical 0-15 + 4 E-cores 16-19)
                         Windows 11.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(os.environ.get("VERBATIM_ROOT", Path(__file__).resolve().parent))

# Input sources (read-only — pipeline never writes here)
MATERIAL_DIR = PROJECT_ROOT / "Material"

# Persistent intermediate artifacts (gitignored — deliberate, not temp)
ACAPELLA_DIR   = PROJECT_ROOT / "01_acapella"
RAW_JSON_DIR   = PROJECT_ROOT / "02_raw_json"
POLISHED_DIR   = PROJECT_ROOT / "03_polished"
VOICEPRINT_DIR = PROJECT_ROOT / "_voiceprints"
LOG_DIR        = PROJECT_ROOT / "_logs"

CORPUS_FILE      = PROJECT_ROOT / "corpus.json"
SESSION_MAP_FILE = PROJECT_ROOT / "session_map.json"

GLOSSARY_DIR = PROJECT_ROOT / "glossaries"
GLOSSARY_EN  = GLOSSARY_DIR / "glossary_en.json"
GLOSSARY_RO  = GLOSSARY_DIR / "glossary_ro.json"

# Directories that must exist before any stage runs.
PIPELINE_DIRS = (
    ACAPELLA_DIR, RAW_JSON_DIR, POLISHED_DIR,
    VOICEPRINT_DIR, LOG_DIR, GLOSSARY_DIR,
)

# ---------------------------------------------------------------------------
# Secrets (environment-sourced — never hardcoded)
# ---------------------------------------------------------------------------

HF_TOKEN          = os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# ---------------------------------------------------------------------------
# Participants / language
# ---------------------------------------------------------------------------

DEFAULT_TEACHER_ID  = "ionut"
SUPPORTED_LANGUAGES = ("en", "ro")

# ---------------------------------------------------------------------------
# Stage 1 — vocal isolation (MelBand Roformer via audio-separator)
# ---------------------------------------------------------------------------

SEPARATOR_MODEL       = "mel_band_roformer_vocals_fv4_gabox.ckpt"
SEPARATOR_BATCH_SIZE  = 4
SPECTRAL_GATE_DB      = -40.0   # post-separation cleanup; below this → zero

# ---------------------------------------------------------------------------
# Stage 3 — Silero VAD pre-filter
# ---------------------------------------------------------------------------

VAD_THRESHOLD        = 0.5
VAD_MIN_SPEECH_MS    = 250
VAD_MIN_SILENCE_MS   = 100
VAD_MERGE_GAP_MS     = 2000     # glue speech segments <this apart

# ---------------------------------------------------------------------------
# Stage 4 — CPU decode (parallel, P-core pinned)
# ---------------------------------------------------------------------------

P_CORE_AFFINITY     = list(range(16))   # i7-12700K P-core logicals
DECODE_WORKERS      = 6
DECODE_SAMPLE_RATE  = 16_000            # Whisper standard

# ---------------------------------------------------------------------------
# Stage 5 — WhisperX ASR (Pascal-specific, DO NOT TOUCH)
# ---------------------------------------------------------------------------

# int8_float32 is NATIVE-fast on Pascal via DP4A.
# FP16 and int8_float16 are 1/64 speed on this GPU — physically gimped.
WHISPER_MODEL        = "large-v3-turbo"
WHISPER_COMPUTE_TYPE = "int8_float32"
WHISPER_BATCH_SIZE   = 16
WHISPER_DEVICE       = "cuda"

CONDITION_ON_PREVIOUS_TEXT         = False
WORD_TIMESTAMPS_FROM_ALIGNMENT_ONLY = True

# Hard-locked per-language hints. Used only when filename specifies language.
INITIAL_PROMPTS = {
    "en": (
        "Vocal lesson terminology: passaggio, appoggio, messa di voce, "
        "sotto voce, tessitura, fach, bel canto, coloratura, squillo, "
        "chiaroscuro, portamento, legato, staccato, marcato, falsetto, "
        "head voice, chest voice, mixed voice, formant, register, "
        "diaphragm, larynx."
    ),
    "ro": (
        "Termeni de canto: pasagio, apodgio, tesitură, voce di petto, "
        "voce di testa, falsetto, solfegiu, interval, formantă, "
        "registru vocal, acut, mediu, grav, legato, staccato, "
        "diafragmă, laringe."
    ),
}

# ---------------------------------------------------------------------------
# Stage 6 — WhisperX forced alignment (wav2vec2)
# ---------------------------------------------------------------------------

ALIGN_MODELS = {
    "en": "WAV2VEC2_ASR_BASE_960H",
    "ro": "jonatasgrosman/wav2vec2-large-xlsr-53-romanian",
}

# ---------------------------------------------------------------------------
# Stage 7 — pyannote diarization
# ---------------------------------------------------------------------------

DIARIZATION_MODEL    = "pyannote/speaker-diarization-3.1"
MIN_SPEAKERS         = 2     # vocal lessons are always dyadic
MAX_SPEAKERS         = 2
DIARIZATION_SEMAPHORE = 2    # simultaneous CPU diarizers

# ---------------------------------------------------------------------------
# Stage 8 — Person identification (voice libraries)
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = "pyannote/embedding"
EMBEDDING_DIM   = 512

VOICE_LIB_MIN_REGION_SECONDS = 10.0   # min per-region audio to update centroid
RECENT_BUFFER_SIZE           = 10     # rolling last-N-sessions ring buffer

# Voiceprint poisoning guards (§7 of brief)
NEW_PERSON_CONFIDENCE_GATE   = 0.75   # first 3 sessions must clear this
UPDATE_REJECTION_THRESHOLD   = 0.65   # below this → no library update
DRIFT_WARNING_THRESHOLD      = 0.15   # warn if session shifts centroid >this
COLLISION_THRESHOLD          = 0.80   # flag person-pair similarity >this

# Verification pass (short-turn reassignment)
SPEAKER_VERIFICATION_ENABLED    = True
VERIFICATION_MAX_TURN_SECONDS   = 3.0
VERIFICATION_REASSIGN_MARGIN    = 0.15  # cosine margin required to flip label

# ---------------------------------------------------------------------------
# Vocal region classifier (pitch-based)
# ---------------------------------------------------------------------------

PITCH_EXTRACTOR          = "pyworld"  # alt: "librosa"
PYWORLD_FRAME_PERIOD_MS  = 10.0       # frame_period arg to pyworld.dio; consumed by regionizer
REGION_LABELS       = ("speaking", "sung_low", "sung_mid", "sung_high", "sung_full")
SUSTAIN_MIN_SECONDS = 1.5        # sung_full = pitch held stable >this

# ---------------------------------------------------------------------------
# Stage 9 — Term-fix polish
# ---------------------------------------------------------------------------

POLISH_ENGINE            = "cli"    # "cli" uses local Claude Code; "api" uses Anthropic SDK
POLISH_SKIP_AVG_LOGPROB  = -0.3     # segments above this skip polish (high-confidence)
POLISH_CHUNK_SIZE        = 200      # segments per LLM call
POLISH_OVERLAP           = 2        # boundary segments duplicated between chunks

ANTHROPIC_MODEL      = "claude-sonnet-4-6"
CLAUDE_CLI_TIMEOUT_S = 120

# ---------------------------------------------------------------------------
# Stage 10 — Corpus & redo mode
# ---------------------------------------------------------------------------

PIPELINE_VERSION        = "1.0.0"
REDO_THRESHOLD_SESSIONS = 3      # --threshold default for `run.py --redo`
REDO_CONFIDENCE_FLOOR   = 0.70   # --confidence-below default
MIN_FREE_DISK_GB        = 400    # preflight check in run.py

# ---------------------------------------------------------------------------
# Reliability
# ---------------------------------------------------------------------------

RETRY_BUDGET    = 3
RETRY_BACKOFF_S = (2, 8, 30)     # sleep intervals per attempt

# Whisper hallucinations on silence — post-filter list.
KNOWN_HALLUCINATIONS = (
    "thank you for watching",
    "thanks for watching",
    "subscribe to the channel",
    "please like and subscribe",
    "like and subscribe",
    "mulțumesc pentru vizionare",
)
