# Vocality — packaging guide

Two pieces to ship:

1. **`vocality-engine.exe`** — PyInstaller-frozen Python daemon. Goes
   inside the Electron installer as `resources/engine/`.
2. **`Vocality Setup X.Y.Z.exe`** — electron-builder NSIS installer that
   carries the engine bundle + the renderer + auto-updater.

---

## Prerequisites

- Python 3.11 venv at `.venv/` with every runtime dep from
  `requirements.txt` installed and **confirmed working** on this machine
  (i.e., `python run.py` on a real file succeeded).
- `pip install pyinstaller` inside the venv.
- Node 20+ with `npm install` run in `vocality-electron/`.

## Full build

From the repo root:

```bash
# 1) Freeze the Python engine. Overwrites vocality-electron/engine/
.venv/Scripts/python.exe -m PyInstaller --noconfirm \
    --distpath vocality-electron build-engine.spec

# 2) Build the Windows installer. Produces vocality-electron/dist/
cd vocality-electron
npm run build-win
```

Outputs:

- `vocality-electron/engine/vocality-engine.exe`
- `vocality-electron/engine/_internal/` (~3–5 GB: torch, CUDA DLLs,
  pyannote, whisperx, audio-separator runtimes)
- `vocality-electron/dist/Vocality Setup X.Y.Z.exe`
- `vocality-electron/dist/latest.yml` (electron-updater manifest)

Model weights are **NOT** bundled. They're fetched from Hugging Face on
first run into `~\.cache\huggingface\` — the user must have `HF_TOKEN`
configured (Settings modal) before running the first batch.

## Auto-update release flow

Set `GH_TOKEN` to a PAT with `repo` scope when publishing. electron-
builder uploads `latest.yml` + the NSIS installer to a GitHub release.

```bash
cd vocality-electron
GH_TOKEN=ghp_xxx npx electron-builder --win --publish always --config build-config/electron-builder.yml
```

The Vocality app's `electron-updater` checks `latest.yml` on each
startup and downloads/installs updates in the background.

## Known build-time gotchas

- **`collect_all` warnings at spec-parse time** are normal for packages
  not installed in the current venv (e.g., `pyannote.metrics` is
  optional). The build still succeeds.
- **UPX is disabled** in the spec — compressed torch/ctranslate2 DLLs
  fail Windows' DLL-load integrity checks at runtime.
- **`engine/` is destroyed** on every PyInstaller run. Anything you
  want to keep in that dir must live elsewhere. This doc used to sit
  at `engine/README.md` and got blown away, hence its move here.
- **`audio-separator[gpu]`** must match the venv's torch CUDA build.
  Mismatched versions ship broken CUDA kernels into the bundle.

## Ship-gate checklist

Before cutting a release:

- [ ] `python run.py` succeeds on a test fixture from `Material/test_smoke/`
- [ ] `npm test` passes in `vocality-electron/` (currently 78 tests)
- [ ] `python -m pytest tests/` passes on the Python side (69 non-GPU)
- [ ] Bump `version` in `vocality-electron/package.json`
- [ ] Tag the commit: `git tag -a v0.X.Y -m "..."; git push --tags`
- [ ] Run the publish command above
- [ ] Smoke-test the installed MSI on a clean VM
