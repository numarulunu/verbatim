# engine/

This directory is **regenerated** on every build by PyInstaller — don't
keep hand-edited files here, they will be wiped.

At build time, `build-engine.spec` at the repo root produces:

- `vocality-engine.exe` — daemon entry point (frozen `engine_daemon.py`)
- `_internal/` — Python runtime + native extensions (~3–5 GB)

electron-builder's `extraResources` copies this whole directory into the
NSIS installer.

See `docs/packaging.md` for the full build procedure.
