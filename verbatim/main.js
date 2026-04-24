/**
 * Verbatim — Electron main process.
 *
 * Owns the single `EngineManager` instance for the whole app lifetime:
 * spawn on ready, stop on quit. Events from the daemon are forwarded to
 * the renderer via `webContents.send('verbatim:event', ...)`. Commands
 * from the renderer arrive through `ipcMain.handle('verbatim:send', ...)`
 * and go straight to `engine.send()`.
 *
 * Future gates add: tray, auto-updater, settings dialog (6G).
 */
'use strict';

const { app, BrowserWindow, dialog, ipcMain, safeStorage, shell } = require('electron');
const path = require('node:path');
const { EngineManager, STATUS } = require('./engine-manager.js');
const { defaultDataDir, resolveEngineCommand, resolveRendererTarget } = require('./runtime-helpers.js');
const fs = require('node:fs');
const { shouldStartBackgroundServices } = require('./startup-policy.js');
const { buildStatusEnvelope } = require('./status-envelope.js');
const { createUpdateStatusState } = require('./update-status-state.js');
const { normalizeUpdaterMessage } = require('./updater-message.js');
const { runWindowControlAction } = require('./window-controls.js');
const { createLogSink } = require('./log-sink.js');
const { loadSettings: loadSettingsStore, saveSettings: saveSettingsStore } = require('./settings-store.js');
const { openPathAction } = require('./open-path-handler.js');
const { migratePlaintext, readSecret, encryptValue } = require('./secret-store.js');

// electron-updater is an optional dependency at dev time (unused until
// a packaged build hits an installed user's machine). Import lazily so
// `npm start` in a fresh clone works even if node_modules is partial.
function loadAutoUpdater() {
  try {
    return require('electron-updater').autoUpdater;
  } catch (_) {
    return null;
  }
}

let mainWindow = null;
let engine = null;
let logSink = null;
const updateStatusState = createUpdateStatusState();

function settingsFilePath() {
  return path.join(app.getPath('userData'), 'verbatim-settings.json');
}

function loadSettings() {
  const result = loadSettingsStore(settingsFilePath());
  return result.settings;
}

/**
 * One-shot migration on boot: if the on-disk settings file still has
 * plaintext tokens and safeStorage is available, encrypt + rewrite. No-op
 * when nothing needs upgrading.
 */
function migrateSecretsOnBoot() {
  const current = loadSettings();
  const { settings: upgraded, changed } = migratePlaintext(current, safeStorage);
  if (changed) {
    try {
      saveSettingsStore(settingsFilePath(), upgraded);
      console.log('[settings] plaintext secrets migrated to safeStorage');
    } catch (err) {
      console.warn('[settings] secret migration failed:', err && err.message);
    }
  }
}

/**
 * Persist settings. Secret fields in the incoming payload are encrypted
 * before writing; plaintext keys are dropped so callers can pass a mixed
 * blob from the renderer without worrying about the on-disk shape.
 */
function saveSettings(settings) {
  const next = { ...(settings || {}) };
  if (typeof next.hf_token === 'string' && next.hf_token !== '') {
    const enc = encryptValue(safeStorage, next.hf_token);
    if (enc) { next.hf_token_encrypted = enc; delete next.hf_token; }
  } else if (next.hf_token === '') {
    // Explicit clear from the UI → drop both variants.
    delete next.hf_token;
    delete next.hf_token_encrypted;
  }
  if (typeof next.anthropic_api_key === 'string' && next.anthropic_api_key !== '') {
    const enc = encryptValue(safeStorage, next.anthropic_api_key);
    if (enc) { next.anthropic_api_key_encrypted = enc; delete next.anthropic_api_key; }
  } else if (next.anthropic_api_key === '') {
    delete next.anthropic_api_key;
    delete next.anthropic_api_key_encrypted;
  }
  saveSettingsStore(settingsFilePath(), next);
}

function resolveDataDir(settings) {
  // Explicit user choice wins.
  if (settings.data_dir && typeof settings.data_dir === 'string' && settings.data_dir.trim()) {
    return settings.data_dir;
  }
  // Default: %LOCALAPPDATA%\Verbatim\data on Windows, equivalent on other
  // platforms via app.getPath('appData'). Packaged builds install to
  // Program Files, which is read-only for normal users — the daemon MUST
  // write outside that tree. See runtime-helpers.js:defaultDataDir doc.
  try {
    const localAppData = process.env.LOCALAPPDATA || app.getPath('appData');
    return defaultDataDir(localAppData);
  } catch (_) {
    // Last-resort fallback so a missing env var never breaks startup.
    return path.join(app.getPath('appData'), 'Verbatim', 'data');
  }
}

function daemonEnv() {
  const settings = loadSettings();
  const env = { ...process.env };
  const hf   = readSecret(settings, 'hf_token', safeStorage);
  const anth = readSecret(settings, 'anthropic_api_key', safeStorage);
  if (hf)   env.HF_TOKEN = hf;
  if (anth) env.ANTHROPIC_API_KEY = anth;
  const dataDir = resolveDataDir(settings);
  // Create the tree so the daemon's utils/engine_lock.mkdir() works on
  // fresh installs. Tolerate races (recursive=true) and platform quirks.
  try { fs.mkdirSync(dataDir, { recursive: true }); } catch (_) { /* best-effort */ }
  env.VERBATIM_ROOT = dataDir;
  return env;
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 960,
    minHeight: 640,
    title: 'Verbatim',
    backgroundColor: '#111111',
    frame: false,
    autoHideMenuBar: true,
    // Security (non-negotiable per brief §3).
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  let rendererLoaded = false;

  const target = resolveRendererTarget({
    isPackaged: app.isPackaged,
    rendererUrl: process.env.VERBATIM_RENDERER_URL || '',
    appDir: __dirname,
    resourcesPath: process.resourcesPath,
  });

  try {
    if (target.kind === 'url') {
      await mainWindow.loadURL(target.value);
    } else {
      await mainWindow.loadFile(target.value);
    }
    rendererLoaded = true;
  } catch (err) {
    console.error('[window] failed to load renderer:', err && err.message ? err.message : err);
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Navigation guards. A compromised renderer (XSS via a future preview, a
  // bad paste, or a CDN-injected resource) could try to open external URLs
  // or navigate the main window off file://. Preload privileges ride along
  // with the origin, so keeping the renderer pinned to its entry point is
  // non-negotiable. Route any user-initiated external link through
  // shell.openExternal instead.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url && /^https?:\/\//i.test(url)) {
      shell.openExternal(url).catch(() => { /* best-effort */ });
    }
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (evt, url) => {
    try {
      const next = new URL(url);
      const current = new URL(mainWindow.webContents.getURL());
      if (next.origin !== current.origin) {
        evt.preventDefault();
        if (next.protocol === 'http:' || next.protocol === 'https:') {
          shell.openExternal(url).catch(() => { /* best-effort */ });
        }
      }
    } catch (_) {
      evt.preventDefault();
    }
  });

  // Renderer crash recovery. Without these, an OOM or native-module fault in
  // the renderer leaves a white window with no diagnostic and no recovery.
  // Auto-reload once; escalate to a fatal-banner event on a second crash so
  // we don't enter a reload loop.
  let renderCrashCount = 0;
  mainWindow.webContents.on('render-process-gone', (_evt, details) => {
    renderCrashCount += 1;
    console.error(
      `[window] renderer gone: reason=${details.reason} exitCode=${details.exitCode} (crash #${renderCrashCount})`,
    );
    if (renderCrashCount <= 1 && mainWindow && !mainWindow.isDestroyed()) {
      try { mainWindow.reload(); } catch (_) { /* ignore */ }
    } else {
      sendToRenderer('verbatim:event', {
        type: 'error',
        error_type: 'renderer_crash',
        title: 'Renderer crashed repeatedly',
        body: `reason=${details.reason} exitCode=${details.exitCode}`,
        recoverable: false,
      });
    }
  });
  mainWindow.webContents.on('unresponsive', () => {
    console.warn('[window] renderer unresponsive');
  });

  return rendererLoaded;
}

function sendToRenderer(channel, payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, payload);
  }
}

async function startEngine() {
  const { command, args, cwd } = resolveEngineCommand(
    app.isPackaged,
    process.resourcesPath,
    __dirname,
  );
  engine = new EngineManager({
    pythonPath: command,
    args,
    cwd,
    env: daemonEnv(),
    onStderr: (chunk) => {
      if (logSink) logSink.append('stderr', chunk.toString('utf8').replace(/\n$/, ''));
    },
  });
  engine.onEvent((evt) => sendToRenderer('verbatim:event', evt));
  engine.onStatus(() => sendToRenderer('verbatim:status', buildStatusEnvelope(engine)));

  try {
    await engine.spawn();
  } catch (err) {
    // Surface the failure so the renderer can show a fatal banner.
    sendToRenderer('verbatim:event', {
      type: 'error',
      error_type: 'daemon_crash',
      message: `engine failed to start: ${err.message}`,
      recoverable: false,
      stderr_tail: engine && engine.stderrTail ? engine.stderrTail : '',
    });
  }
}

function registerIpcHandlers() {
  ipcMain.handle('verbatim:send', (_evt, command) => {
    if (!engine) throw new Error('engine not initialised');
    engine.send(command);
    return { ok: true };
  });
  ipcMain.handle('verbatim:status', () => {
    return buildStatusEnvelope(engine);
  });
  ipcMain.handle('verbatim:update-status', () => updateStatusState.current());
  ipcMain.handle('verbatim:window-control', (_evt, action) => runWindowControlAction(mainWindow, action));
  ipcMain.handle('verbatim:restart', async () => {
    if (engine) await engine.stop();
    await startEngine();
    return { ok: true };
  });
  ipcMain.handle('verbatim:pick-folder', async (_evt, defaultPath) => {
    const result = await dialog.showOpenDialog(mainWindow ?? undefined, {
      properties: ['openDirectory'],
      defaultPath: typeof defaultPath === 'string' && defaultPath ? defaultPath : undefined,
    });
    return result.canceled ? null : result.filePaths[0] ?? null;
  });
  ipcMain.handle('verbatim:open-path', async (_evt, targetPath) => {
    // Confine reveals to the user's profile and reject executable file
    // types. See open-path-handler.js for the full rationale.
    return openPathAction({
      targetPath,
      shellOpenPath: (p) => shell.openPath(p),
      allowedRoots: [app.getPath('home')],
    });
  });
  ipcMain.handle('verbatim:install-update-now', () => {
    // Explicit user-initiated install. electron-updater returns void; any
    // error surfaces through the `error` event already relayed to the UI.
    const autoUpdater = loadAutoUpdater();
    if (!autoUpdater) return { ok: false, error: 'Updater not available' };
    try {
      autoUpdater.quitAndInstall(false, true);
      return { ok: true, error: null };
    } catch (err) {
      return { ok: false, error: err && err.message ? err.message : 'Install failed' };
    }
  });
  ipcMain.handle('verbatim:open-logs-folder', async () => {
    if (!logSink) return { ok: false, error: 'log sink not initialised' };
    const error = await shell.openPath(logSink.dir);
    return { ok: error.length === 0, error: error || null, path: logSink.dir };
  });
  ipcMain.handle('verbatim:get-settings', () => {
    // Decrypt secrets before handing them to the renderer so the Settings
    // modal can populate its text fields. Plaintext only exists in RAM
    // between this call and the next save.
    const settings = loadSettings();
    const out = { ...settings };
    const hf   = readSecret(settings, 'hf_token', safeStorage);
    const anth = readSecret(settings, 'anthropic_api_key', safeStorage);
    if (hf)   out.hf_token = hf;
    if (anth) out.anthropic_api_key = anth;
    delete out.hf_token_encrypted;
    delete out.anthropic_api_key_encrypted;
    return out;
  });
  ipcMain.handle('verbatim:save-settings', (_evt, settings) => {
    saveSettings(settings);
    return { ok: true };
  });
}

/**
 * Wire electron-updater. No-op in dev (isPackaged=false) because the
 * updater refuses to run against an unsigned, unpackaged app and the
 * GitHub Releases endpoint has nothing to offer yet.
 *
 * Relays every lifecycle event to the renderer as
 * {channel: 'verbatim:update-status', kind, ...payload} so the UI can
 * surface "Update available — downloading" / "Update ready to install"
 * banners. Silent fallback if electron-updater isn't installed.
 */
function initAutoUpdater() {
  if (!app.isPackaged) {
    console.log('[updater] skipped — dev mode');
    return;
  }
  const autoUpdater = loadAutoUpdater();
  if (!autoUpdater) {
    console.warn('[updater] electron-updater not installed; auto-update disabled');
    return;
  }
  // Download new builds in the background, but DO NOT auto-install on quit
  // until the installer is signed (SMAC Finding 6). Unsigned auto-install
  // across a public GitHub Releases feed is a silent-RCE vector. Instead
  // the renderer exposes a manual "Install now" action once the update is
  // ready.
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = false;
  autoUpdater.allowDowngrade = false;
  autoUpdater.logger = console;

  const relay = (kind, payload = {}) => {
    const next = updateStatusState.set({ kind, ...payload });
    sendToRenderer('verbatim:update-status', next);
  };

  autoUpdater.on('checking-for-update',    () => relay('checking'));
  autoUpdater.on('update-available',       (info) => relay('available', { version: info.version }));
  autoUpdater.on('update-not-available',   () => relay('current'));
  autoUpdater.on('error',                  (err) => relay('error', { message: normalizeUpdaterMessage(err) }));
  autoUpdater.on('download-progress',      (p) => relay('downloading', {
    percent: p.percent, bytes_per_second: p.bytesPerSecond,
  }));
  autoUpdater.on('update-downloaded',      (info) => relay('downloaded', { version: info.version }));

  autoUpdater.checkForUpdatesAndNotify().catch((err) => {
    console.warn('[updater] initial check failed:', err && err.message);
  });
}

// Single-instance lock (brief §3). A second launch focuses the existing window.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    try {
      logSink = createLogSink(app.getPath('logs'));
      logSink.install();
      console.log('[main] log sink ready:', logSink.logPath);
    } catch (err) {
      // Sink failure is never fatal — fall back to the unattached console.
      console.warn('[main] log sink unavailable:', err && err.message ? err.message : err);
    }
    migrateSecretsOnBoot();
    registerIpcHandlers();
    let rendererLoaded = false;
    try {
      rendererLoaded = await createWindow();
    } catch (err) {
      console.error('[window] failed to create window:', err && err.message ? err.message : err);
    }
    if (!shouldStartBackgroundServices(rendererLoaded)) {
      return;
    }
    await startEngine();
    initAutoUpdater();
  });

  app.on('window-all-closed', () => {
    // Windows/Linux: quit on last window close. macOS: keep app running
    // (convention; even though macOS support is deferred per §1).
    if (process.platform !== 'darwin') app.quit();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      void createWindow().catch((err) => {
        console.error('[window] activate failed:', err && err.message ? err.message : err);
      });
    }
  });

  app.on('before-quit', async (event) => {
    if (engine && engine.status !== STATUS.DOWN && engine.status !== STATUS.CRASHED) {
      event.preventDefault();
      try {
        await engine.stop();
      } catch (_) { /* swallow — we're quitting */ }
      engine = null;
      app.quit();
    }
  });
}
