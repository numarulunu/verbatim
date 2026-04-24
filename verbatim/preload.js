/**
 * Verbatim preload — whitelist-only bridge between main and renderer.
 *
 * Security constraints (brief §3):
 *   - contextIsolation: true (enforced in main.js)
 *   - nodeIntegration: false
 *   - No Node APIs or ipcRenderer handles leaked to the renderer
 *   - Every channel named explicitly; no wildcards
 */
'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('verbatim', {
  minimizeWindow: () => ipcRenderer.invoke('verbatim:window-control', 'minimize'),
  toggleMaximizeWindow: () => ipcRenderer.invoke('verbatim:window-control', 'toggle-maximize'),
  closeWindow: () => ipcRenderer.invoke('verbatim:window-control', 'close'),

  /**
   * Send a command to the daemon. Resolves once main has forwarded it
   * (does NOT wait for a matching event — subscribe via onEvent + filter
   * on command id for that).
   */
  send: (command) => ipcRenderer.invoke('verbatim:send', command),

  /**
   * Subscribe to daemon events. The callback receives parsed event
   * objects (the `type` discriminator and whatever fields the event
   * carries). Returns an unsubscribe function.
   */
  onEvent: (cb) => {
    const listener = (_evt, payload) => cb(payload);
    ipcRenderer.on('verbatim:event', listener);
    return () => ipcRenderer.removeListener('verbatim:event', listener);
  },

  /**
   * Subscribe to daemon status transitions ('down' | 'spawning' | 'ready'
   * | 'shutting_down' | 'crashed'). Returns an unsubscribe function.
   */
  onStatus: (cb) => {
    const listener = (_evt, payload) => cb(payload);
    ipcRenderer.on('verbatim:status', listener);
    return () => ipcRenderer.removeListener('verbatim:status', listener);
  },

  /** Synchronously-ish fetch the current daemon status + last ready event. */
  status: () => ipcRenderer.invoke('verbatim:status'),

  /** Restart the daemon (after crash or for a fresh run). */
  restart: () => ipcRenderer.invoke('verbatim:restart'),

  pickFolder: (defaultPath) => ipcRenderer.invoke('verbatim:pick-folder', defaultPath),

  openPath: (targetPath) => ipcRenderer.invoke('verbatim:open-path', targetPath),

  /** Open the main-process log folder in the OS file browser. */
  openLogsFolder: () => ipcRenderer.invoke('verbatim:open-logs-folder'),

  /** Read the persisted user settings (HF/Anthropic tokens, data dir). */
  getSettings: () => ipcRenderer.invoke('verbatim:get-settings'),

  /** Persist settings to userData and return {ok: true}. Caller usually
   *  follows up with verbatim.restart() so the daemon picks them up. */
  saveSettings: (s) => ipcRenderer.invoke('verbatim:save-settings', s),

  /** Subscribe to electron-updater lifecycle events. `kind` is one of
   *  'checking' | 'available' | 'current' | 'downloading' | 'downloaded'
   *  | 'error'. No events in dev mode. */
  updateStatus: () => ipcRenderer.invoke('verbatim:update-status'),

  onUpdateStatus: (cb) => {
    const listener = (_evt, payload) => cb(payload);
    ipcRenderer.on('verbatim:update-status', listener);
    return () => ipcRenderer.removeListener('verbatim:update-status', listener);
  },

  /** Trigger auto-installer after an update has been downloaded. Explicit
   *  user action: install happens immediately and the app relaunches. */
  installUpdateNow: () => ipcRenderer.invoke('verbatim:install-update-now'),
});
