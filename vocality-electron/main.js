/**
 * Vocality — Electron main process.
 *
 * Owns the single `EngineManager` instance for the whole app lifetime:
 * spawn on ready, stop on quit. Events from the daemon are forwarded to
 * the renderer via `webContents.send('vocality:event', ...)`. Commands
 * from the renderer arrive through `ipcMain.handle('vocality:send', ...)`
 * and go straight to `engine.send()`.
 *
 * Future gates add: tray, auto-updater, settings dialog (6G).
 */
'use strict';

const { app, BrowserWindow, ipcMain } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { EngineManager, STATUS } = require('./engine-manager.js');
const { resolveEngineCommand } = require('./runtime-helpers.js');

let mainWindow = null;
let engine = null;

function settingsFilePath() {
  return path.join(app.getPath('userData'), 'vocality-settings.json');
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
  if (settings.data_dir)          env.VOCALITY_ROOT = settings.data_dir;
  return env;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    title: 'Vocality',
    backgroundColor: '#111111',
    // Security (non-negotiable per brief §3).
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'resources', 'index.html'));

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
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
  engine.onEvent((evt) => sendToRenderer('vocality:event', evt));
  engine.onStatus((s) => sendToRenderer('vocality:status', s));

  try {
    await engine.spawn();
  } catch (err) {
    // Surface the failure so the renderer can show a fatal banner.
    sendToRenderer('vocality:event', {
      type: 'error',
      error_type: 'daemon_crash',
      message: `engine failed to start: ${err.message}`,
      recoverable: false,
    });
  }
}

function registerIpcHandlers() {
  ipcMain.handle('vocality:send', (_evt, command) => {
    if (!engine) throw new Error('engine not initialised');
    engine.send(command);
    return { ok: true };
  });
  ipcMain.handle('vocality:status', () => {
    if (!engine) return { status: STATUS.DOWN, lastReady: null };
    return { status: engine.status, lastReady: engine.lastReady };
  });
  ipcMain.handle('vocality:restart', async () => {
    if (engine) await engine.stop();
    await startEngine();
    return { ok: true };
  });
  ipcMain.handle('vocality:get-settings', () => loadSettings());
  ipcMain.handle('vocality:save-settings', (_evt, settings) => {
    saveSettings(settings);
    return { ok: true };
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
    createWindow();
    await startEngine();
  });

  app.on('window-all-closed', () => {
    // Windows/Linux: quit on last window close. macOS: keep app running
    // (convention; even though macOS support is deferred per §1).
    if (process.platform !== 'darwin') app.quit();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
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
