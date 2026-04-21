/**
 * Vocality renderer — GATE-3 scaffold.
 *
 * Real UI logic (view switcher, IPC wiring, progress rendering, reducer loop)
 * lands in Gate 6. For now this just proves the preload's contextBridge is
 * reachable so we know the security pipeline is wired up correctly.
 */
'use strict';

document.addEventListener('DOMContentLoaded', () => {
  const status = document.getElementById('status');
  if (status && window.vocality) {
    status.textContent = `scaffold v${window.vocality.version} — daemon not yet connected`;
  } else if (status) {
    status.textContent = 'ERROR: contextBridge not wired; check preload.js';
  }
});
