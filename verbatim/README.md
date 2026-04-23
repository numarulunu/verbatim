# verbatim

Electron desktop wrapper for the Verbatim ASR pipeline. The Electron shell stays in `verbatim/`; the primary renderer now lives in `verbatim/renderer/` as a Vite + React app loaded through the existing preload bridge.

## Development

```bash
cd verbatim
npm install
npm --prefix renderer install
npm test
```

Renderer-only development:

```bash
cd verbatim
npm run renderer:dev
```

Electron + React renderer development:

```bash
cd verbatim
$env:VERBATIM_RENDERER_URL='http://127.0.0.1:5173'
npm start
```

`VERBATIM_RENDERER_URL` tells Electron to load the live Vite server. Without it, `npm start` builds `renderer/dist/` first and opens the built renderer.

## Build

```bash
cd verbatim
npm run build-win
```

That builds `verbatim/renderer/dist/` and then runs `electron-builder` with `build-config/electron-builder.yml`.

## Layout

```text
verbatim/
|- package.json
|- main.js
|- preload.js
|- runtime-helpers.js
|- renderer/                 # primary React renderer workspace
|  |- src/
|  |- dist/                  # production renderer output
|- engine/                   # PyInstaller drop zone
|- tests/
|  |- runtime-helpers.test.js
|  |- renderer-normalize.test.js
|  |- packaged-engine.test.js
|- build-config/
   |- electron-builder.yml
```

## Notes

- `window.verbatim` remains the only privileged renderer surface.
- Packaged builds resolve the renderer from `resources/app.asar/renderer/dist/index.html`.
- The Python engine is still bundled through `extraResources` under `resources/engine/`.
