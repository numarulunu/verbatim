# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the Vocality engine daemon.

Builds a one-folder bundle at `vocality-electron/engine/vocality-engine/`
that electron-builder's `extraResources` copies into the installer.

Run from repo root:
    pip install pyinstaller
    pyinstaller --noconfirm --distpath vocality-electron build-engine.spec

Expected output (COLLECT name='engine' sits under distpath):
    vocality-electron/engine/vocality-engine.exe
    vocality-electron/engine/_internal/             (Python runtime + deps)

The runtime helper `resolveEngineCommand` in vocality-electron/ expects
`engine/vocality-engine.exe` at exactly that path.

Note: PyInstaller cannot statically bundle the ML models themselves (too
large, downloaded to a cache dir at first run). The user's HF_TOKEN must
be set at runtime; see the Settings modal.

Known gotchas, all handled below:
- pyannote / speechbrain / whisperx / transformers pull a forest of
  hidden imports that PyInstaller's analyser doesn't catch. `collect_all`
  solves those pkg-by-pkg.
- Some packages use `pkg_resources` to look up their installed version or
  metadata at import time — `copy_metadata` bundles the `*.dist-info`
  directory so those lookups keep working inside the frozen bundle.
- ctranslate2 + torch ship CUDA DLLs that only work when they land next
  to the exe. PyInstaller places them in `_internal/` automatically; the
  installer preserves that structure.
- audio-separator downloads models on first run — none bundled here.
"""
import os
from PyInstaller.utils.hooks import collect_all, copy_metadata


# Packages that PyInstaller's static analysis misses entry points / data
# files for. `collect_all` returns (datas, binaries, hiddenimports) for
# everything reachable from the package's __init__.
_COLLECT_ALL = [
    'torch',
    'torchaudio',
    'torchvision',
    'ctranslate2',
    'whisperx',
    'faster_whisper',
    'pyannote',
    'pyannote.audio',
    'pyannote.core',
    'pyannote.database',
    'pyannote.metrics',
    'pyannote.pipeline',
    'speechbrain',
    'silero_vad',
    'transformers',
    'tokenizers',
    'sentencepiece',
    'librosa',
    'audio_separator',
    'soundfile',
    'pyworld',
    'anthropic',
    'huggingface_hub',
    'scipy',
    'numpy',
    'psutil',
    'pynvml',
]

# Packages whose dist-info metadata is consulted at runtime (importlib.metadata
# / pkg_resources). Bundle the metadata so `__version__` lookups succeed.
_METADATA = [
    'torch',
    'torchaudio',
    'transformers',
    'tokenizers',
    'huggingface_hub',
    'pyannote.audio',
    'speechbrain',
    'faster-whisper',
    'whisperx',
]


datas = []
binaries = []
hiddenimports = []

for pkg in _COLLECT_ALL:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # noqa: BLE001 — missing package becomes a build-time warning
        print(f"[build-engine] WARN: collect_all({pkg!r}) failed: {exc}")

for pkg in _METADATA:
    try:
        datas += copy_metadata(pkg)
    except Exception as exc:  # noqa: BLE001
        print(f"[build-engine] WARN: copy_metadata({pkg!r}) failed: {exc}")


# Bundle ffmpeg + ffprobe next to vocality-engine.exe so audio-separator
# and utils.audio_qc don't need a system-installed ffmpeg. Populated by
# `node scripts/fetch-ffmpeg.js`.
_FFMPEG_DIR = os.path.join('build', 'ffmpeg', 'bin')
for _name in ('ffmpeg.exe', 'ffprobe.exe'):
    _p = os.path.join(_FFMPEG_DIR, _name)
    if os.path.exists(_p):
        # '.' = dest relative to the COLLECT root (sits beside vocality-engine.exe).
        binaries.append((_p, '.'))
        print(f"[build-engine] bundled {_p}")
    else:
        print(
            f"[build-engine] WARN: {_p} not found — install will require "
            f"{_name} on the system PATH. Run `node scripts/fetch-ffmpeg.js` "
            f"before the spec if you want it bundled."
        )


a = Analysis(
    ['engine_daemon.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        # First-party modules: PyInstaller finds them via imports from
        # engine_daemon, but belt-and-braces to ensure they land even when
        # late-imported.
        'handlers',
        'ipc_protocol',
        'run',
        'stage1_isolate',
        'stage2_transcribe_diarize',
        'stage3_postprocess',
        'persons',
        'persons.corpus',
        'persons.embedder',
        'persons.matcher',
        'persons.redo',
        'persons.registry',
        'persons.regionizer',
        'persons.schema',
        'persons.polish_engine',
        'utils',
        'utils.atomic_audio',
        'utils.atomic_write',
        'utils.audio_qc',
        'utils.cancellation',
        'utils.checkpoint',
        'utils.engine_lock',
        'utils.hf_compat',
        'utils.reporter',
        'utils.retry',
        'utils.silero_vad',
        'utils.text_norm',
        'filename_parser',
        'hw_clamp',
        'config',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Optional dev-only deps — skip to shrink the bundle.
        'pytest',
        'jupyter',
        'matplotlib',
        'tensorflow',
        'tensorboard',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='vocality-engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,   # UPX trips torch's CUDA DLL signature check
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    # Place everything under {distpath}/engine/ so the Electron runtime
    # helper finds vocality-engine.exe at the path it resolves.
    name='engine',
)
