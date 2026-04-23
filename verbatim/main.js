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

const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { EngineManager, STATUS } = require('./engine-manager.js');
const { resolveEngineCommand, resolveRendererTarget } = require('./runtime-helpers.js');
const { shouldStartBackgroundServices } = require('./startup-policy.js');
const { buildStatusEnvelope } = require('./status-envelope.js');
const { createUpdateStatusState } = require('./update-status-state.js');
const { runWindowControlAction } = require('./window-controls.js');

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
const updateStatusState = createUpdateStatusState();

function settingsFilePath() {
  return path.join(app.getPath('userData'), 'verbatim-settings.json');
}

function loadSettings() {
  try {
    return JSON.parse(fs.readFileSync(settingsFilePath(), 'utf8'));
  } catch (_) {
    return {};
  }
}

function saveSettings(settings) {
  const p = settingsFilePath();
  fs.mkdirSync(path.dirname(p), { recursive: true });
  const tmp = p + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(settings || {}, null, 2));
  fs.renameSync(tmp, p);
}

function daemonEnv() {
  const settings = loadSettings();
  const env = { ...process.env };
  if (settings.hf_token)          env.HF_TOKEN = settings.hf_token;
  if (settings.anthropic_api_key) env.ANTHROPIC_API_KEY = settings.anthropic_api_key;
  if (settings.data_dir)          env.VERBATIM_ROOT = settings.data_dir;
  return env;
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 1180,
    minHeight: 760,
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
    if (typeof targetPath !== 'string' || !targetPath.trim()) {
      throw new Error('Path is required');
    }
    const error = await shell.openPath(targetPath);
    return { ok: error.length === 0, error: error || null };
  });
  ipcMain.handle('verbatim:get-settings', () => loadSettings());
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
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.logger = console;

  const relay = (kind, payload = {}) => {
    const next = updateStatusState.set({ kind, ...payload });
    sendToRenderer('verbatim:update-status', next);
  };

  autoUpdater.on('checking-for-update',    () => relay('checking'));
  autoUpdater.on('update-available',       (info) => relay('available', { version: info.version }));
  autoUpdater.on('update-not-available',   () => relay('current'));
  autoUpdater.on('error',                  (err) => relay('error', { message: err && err.message }));
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
