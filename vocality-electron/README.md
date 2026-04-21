# vocality-electron

Electron GUI wrapper for the Vocality ASR pipeline. The Python engine
lives at the repo root (`run.py`, `persons/`, `stage*.py`). This directory
holds the desktop app that drives it.

**Status:** Gate 3 scaffold. Blank window opens; test suite passes against
stubs. IPC contract, daemon supervision, three-view UI, and packaging land
in Gates 4–8 per `../VOCALITY_ELECTRON_BRIEF.md`.

## Quick start (development)

```bash
cd vocality-electron
npm install            # ~200 MB; pulls electron + electron-builder
npm test               # node --test — all stubs pass
npm start              # opens a titled blank window
```

## Directory layout

```
vocality-electron/
├── package.json
├── main.js                  # main process — window + single-instance lock
├── preload.js               # contextBridge — exposes window.vocality.*
├── runtime-helpers.js       # pure-Node helpers (path resolution)
├── app-state.js             # pure reducer for renderer state
├── resources/               # renderer assets
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── engine/                  # PyInstaller drop zone (populated at build time)
│   └── README.md
├── tests/                   # node --test targets
│   ├── app-state.test.js
│   ├── runtime-helpers.test.js
│   └── packaged-engine.test.js
└── build-config/
    └── electron-builder.yml
```

## Brief reference

See `VOCALITY_ELECTRON_BRIEF.md` at the repo root for the full design:
daemon IPC contract, cancellation discipline, data-persistence rules,
error taxonomy, packaging pipeline.
