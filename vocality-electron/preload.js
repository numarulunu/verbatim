/**
 * Vocality preload — whitelist-only bridge between main and renderer.
 *
 * GATE-3 SCAFFOLD. Exposes a minimal `window.vocality` namespace just to
 * prove the contextBridge pathway works. Real IPC channels (every command
 * from brief §4) wire up in Gate 4 under `window.vocality.daemon.*` and
 * `window.vocality.ui.*`.
 *
 * Security constraints (brief §3):
 *   - contextIsolation: true (enforced in main.js)
 *   - nodeIntegration: false
 *   - No Node APIs or ipcRenderer handles leaked to the renderer
 *   - Every channel must be named explicitly; no wildcards
 */
'use strict';

const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('vocality', {
  version: '0.1.0',
  // Gate 4 adds:
  //   daemon: { send: (cmd) => ..., on: (type, cb) => ... }
  //   ui: { openBrowse: () => ..., saveSettings: (s) => ... }
});
