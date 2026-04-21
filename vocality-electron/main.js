/**
 * Vocality — Electron main process.
 *
 * GATE-3 SCAFFOLD. Responsibilities that land later:
 *   - Daemon supervision (Gate 5)
 *   - IPC handler registration (Gate 4)
 *   - Tray + auto-updater + settings (Gate 6/8)
 *
 * This file deliberately does the minimum: create a secure, titled window
 * and hold a single-instance lock. Everything else arrives in later gates.
 */
'use strict';

const { app, BrowserWindow } = require('electron');
const path = require('node:path');

let mainWindow = null;

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

  app.whenReady().then(createWindow);

  app.on('window-all-closed', () => {
    // Windows/Linux: quit on last window close. macOS: keep app running
    // (convention; even though macOS support is deferred per §1).
    if (process.platform !== 'darwin') app.quit();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
}
