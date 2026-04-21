# Verbatim — packaging guide

The build produces a single **`Verbatim Setup X.Y.Z.exe`** (per-machine
NSIS installer, lands in `C:\Program Files\Verbatim\`) that bundles:

- The PyInstaller-frozen Python daemon (`verbatim-engine.exe` +
  `_internal/` with torch, CUDA DLLs, pyannote, whisperx, audio-
  separator).
- `ffmpeg.exe` + `ffprobe.exe` fetched from gyan.dev at build time.
- The Electron renderer + electron-updater.

What's **not** bundled (downloaded on first batch, ~5–8 GB):

- faster-whisper large-v3-turbo weights (~1.5 GB)
- pyannote/speaker-diarization-3.1 + embedding model (~500 MB)
- audio-separator MelBand Roformer weights (~200 MB)
- whisperx wav2vec2 alignment model per language (~1 GB each)

End-user flow: install → launch → Settings modal (enter HF_TOKEN +
optional ANTHROPIC_API_KEY) → Batch tab → Scan → Start. First batch
downloads models; subsequent runs are fully offline.

---

## Prerequisites (build machine)

- Python 3.11 venv at `.venv/` with every runtime dep from
  `requirements.txt` installed and **confirmed working** (i.e.,
  `python run.py` on a real file succeeded).
- `pip install pyinstaller` inside the venv.
- Node 20+ with `npm install` run in `verbatim/`.
- Internet access during the first build (fetches FFmpeg).

## Full build — one command

```bash
cd verbatim
npm run build-all-win
```

That runs, in order:

1. `fetch-ffmpeg` — downloads gyan.dev's essentials build into
   `build/ffmpeg/bin/` (cached; no-op on subsequent builds).
2. `build-engine` — PyInstaller freezes `engine_daemon.py` into
   `verbatim/engine/verbatim-engine.exe` + `_internal/`.
   ffmpeg.exe + ffprobe.exe are bundled alongside.
3. `build-win` — electron-builder produces
   `verbatim/dist/Verbatim Setup X.Y.Z.exe` +
   `latest.yml` for auto-update.

Total build time: ~10–15 min on the first run (FFmpeg download +
PyInstaller collect_all over torch/whisperx/pyannote). Subsequent
builds with warm caches: ~3–5 min.

Output installer size: expect **2–4 GB**. The torch + CUDA DLLs are
the bulk; audio-separator's onnxruntime adds ~200 MB.

## Auto-update release flow

Set `GH_TOKEN` to a PAT with `repo` scope when publishing. electron-
builder uploads `latest.yml` + the NSIS installer to a GitHub release.

```bash
cd verbatim
GH_TOKEN=ghp_xxx npx electron-builder --win --publish always --config build-config/electron-builder.yml
```

The Verbatim app's `electron-updater` checks `latest.yml` on each
startup and downloads/installs updates in the background.

## Known build-time gotchas

- **`collect_all` warnings at spec-parse time** are normal for packages
  not installed in the current venv (e.g., `pyannote.metrics` is
  optional). The build still succeeds.
- **UPX is disabled** in the spec — compressed torch/ctranslate2 DLLs
  fail Windows' DLL-load integrity checks at runtime.
- **`engine/` is destroyed** on every PyInstaller run. Anything you
  want to keep in that dir must live elsewhere (this doc moved out of
  `engine/README.md` for that reason).
- **`audio-separator[gpu]`** must match the venv's torch CUDA build.
  Mismatched versions ship broken CUDA kernels into the bundle.
- **First-launch model download** — the first batch will appear to
  hang for 2–5 min while huggingface_hub fetches weights. The Electron
  UI won't show phase progress until downloads complete. Consider a
  pre-flight warm-up after install (run a dry batch).
- **No icon**: `build-config/electron-builder.yml` no longer requires
  `resources/icon.ico`; electron-builder falls back to default. Drop a
  256×256 `.ico` there whenever you want Verbatim branding in the
  taskbar / installer.

## End-user install experience

1. User runs `Verbatim Setup X.Y.Z.exe`
2. Windows UAC prompt (per-machine install writes to Program Files)
3. Installer offers install location (default `C:\Program Files\Verbatim\`)
4. Desktop + Start Menu shortcuts created, app launches
5. First launch: status bar shows `daemon: spawning → ready`
6. User clicks gear → Settings → enters `HF_TOKEN` (required for
   pyannote / whisper models) and optional `ANTHROPIC_API_KEY`
7. Daemon restarts with env, user switches to Batch → Scan Material
   → Start → watches phase progress (first batch also downloads ~5 GB
   of models; progress bar will pause before phase 4 while HF
   downloads)

After first run, everything is local. No system-level FFmpeg required.

## Uninstall

Settings → Apps & features → Verbatim → Uninstall. Removes
`C:\Program Files\Verbatim\` but **not** the user's data
(`%LOCALAPPDATA%\Verbatim\data\`) — that's deliberate so reinstalling
preserves the voiceprint registry + polished transcripts.

## Ship-gate checklist

Before cutting a release:

- [ ] `python run.py` succeeds on a test fixture from `Material/test_smoke/`
- [ ] `node scripts/daemon-smoke.js` passes (10/10 steps)
- [ ] `npm test` passes in `verbatim/`
- [ ] `python -m pytest tests/test_reporter.py tests/test_handlers.py
      tests/test_engine_lock.py tests/test_phase_events.py` passes
- [ ] Bump `version` in `verbatim/package.json`
- [ ] `npm run build-all-win` succeeds, installer launches on a clean VM
- [ ] Tag the commit: `git tag -a v0.X.Y -m "..."; git push --tags`
- [ ] `GH_TOKEN=ghp_xxx npm run publish-win`
- [ ] Verify `latest.yml` + installer landed on the GitHub release
