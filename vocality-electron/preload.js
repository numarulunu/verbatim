/**
 * Vocality preload — whitelist-only bridge between main and renderer.
 *
 * Security constraints (brief §3):
 *   - contextIsolation: true (enforced in main.js)
 *   - nodeIntegration: false
 *   - No Node APIs or ipcRenderer handles leaked to the renderer
 *   - Every channel named explicitly; no wildcards
 */
'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('vocality', {
  version: '0.1.0',

  /**
   * Send a command to the daemon. Resolves once main has forwarded it
   * (does NOT wait for a matching event — subscribe via onEvent + filter
   * on command id for that).
   */
  send: (command) => ipcRenderer.invoke('vocality:send', command),

  /**
   * Subscribe to daemon events. The callback receives parsed event
   * objects (the `type` discriminator and whatever fields the event
   * carries). Returns an unsubscribe function.
   */
  onEvent: (cb) => {
    const listener = (_evt, payload) => cb(payload);
    ipcRenderer.on('vocality:event', listener);
    return () => ipcRenderer.removeListener('vocality:event', listener);
  },

  /**
   * Subscribe to daemon status transitions ('down' | 'spawning' | 'ready'
   * | 'shutting_down' | 'crashed'). Returns an unsubscribe function.
   */
  onStatus: (cb) => {
    const listener = (_evt, payload) => cb(payload);
    ipcRenderer.on('vocality:status', listener);
    return () => ipcRenderer.removeListener('vocality:status', listener);
  },

  /** Synchronously-ish fetch the current daemon status + last ready event. */
  status: () => ipcRenderer.invoke('vocality:status'),

  /** Restart the daemon (after crash or for a fresh run). */
  restart: () => ipcRenderer.invoke('vocality:restart'),
});
