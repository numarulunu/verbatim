# engine/

Placeholder for the compiled Python engine. At build time, PyInstaller
produces `vocality-engine.exe` (one-folder mode with `_internal/` sibling)
and electron-builder's `extraResources` copies this whole directory into
the installer (brief §9).

## Populated contents at build time

- `vocality-engine.exe` — daemon entry point (see repo-root `engine_daemon.py`)
- `_internal/` — PyInstaller deps: Python runtime + native extensions
- (no model files — downloaded on first run per brief §9)

## Populating manually during development

From the repo root (parent of `vocality-electron/`):

```bash
pip install pyinstaller

pyinstaller --noconfirm \
  --onedir \
  --name vocality-engine \
  --distpath vocality-electron/engine \
  engine_daemon.py
```

The build doesn't land until Gate 5 (engine wrapping); this directory
stays empty apart from this README in Gates 3–4.

## What MUST NOT go here

- Model files (faster-whisper, pyannote, silero). They're ~5–10 GB total
  and downloaded at first run into the user's data directory.
- Voiceprint database. Stored outside the install tree per brief §3.
- Test fixtures. Tests live in `vocality-electron/tests/`.
