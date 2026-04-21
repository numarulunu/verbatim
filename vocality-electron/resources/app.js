/**
 * Vocality renderer — dispatcher + view rendering.
 *
 * - state is owned by the module-level `state` variable
 * - incoming daemon events flow through appState.reduceEvent
 * - UI actions (tab clicks, form submits) dispatch through setView or
 *   custom patches
 * - render() is idempotent; called after every dispatch
 *
 * All daemon IO goes through window.vocality.* (preload bridge).
 */
'use strict';

(() => {
  if (!window.vocality) {
    document.body.innerHTML =
      '<main style="padding:24px;color:#b06a6a">ERROR: preload not wired — window.vocality is missing.</main>';
    return;
  }
  if (!window.appState) {
    document.body.innerHTML =
      '<main style="padding:24px;color:#b06a6a">ERROR: app-state.js not loaded before app.js.</main>';
    return;
  }

  const { initialState, reduceEvent, setView } = window.appState;

  let state = initialState();

  function dispatch(patch) {
    state = typeof patch === 'function' ? patch(state) : patch;
    render();
  }

  // Generate an id for correlating responses to commands.
  let _cmdCounter = 0;
  function nextId(prefix) { return `${prefix}-${Date.now()}-${++_cmdCounter}`; }

  // ── DOM refs ────────────────────────────────────────────────────────

  const statusDot = document.querySelector('.status-dot');
  const statusLabel = document.querySelector('.status-label');
  const statusVersion = document.querySelector('.status-version');
  const statusLastError = document.querySelector('.status-last-error');
  const tabs = Array.from(document.querySelectorAll('.tab'));
  const views = Array.from(document.querySelectorAll('.view'));

  // Batch view
  const batchView = document.querySelector('.view[data-view="batch"]');
  const scanPathInput = batchView.querySelector('.scan-path');
  const scanBtn = batchView.querySelector('[data-action="scan"]');
  const startBtn = batchView.querySelector('[data-action="start"]');
  const cancelBtn = batchView.querySelector('[data-action="cancel"]');
  const batchSummary = batchView.querySelector('.batch-summary');
  const batchFilesEl = batchView.querySelector('.batch-files');
  const fileRowTmpl = document.getElementById('file-row-template');

  // ── Rendering ──────────────────────────────────────────────────────

  function render() {
    renderTabs();
    renderStatusBar();
    renderBatchView();
  }

  function renderTabs() {
    for (const tab of tabs) {
      const isActive = tab.dataset.view === state.view;
      tab.classList.toggle('active', isActive);
      tab.setAttribute('aria-selected', String(isActive));
    }
    for (const v of views) v.hidden = v.dataset.view !== state.view;
  }

  function renderStatusBar() {
    statusDot.dataset.status = state.daemon.status;
    statusLabel.textContent = `daemon: ${state.daemon.status}`;
    statusVersion.textContent = state.daemon.version ? `v${state.daemon.version}` : '';
    const lastError = state.errors[state.errors.length - 1];
    statusLastError.textContent = lastError
      ? `${lastError.error_type}: ${lastError.message}`
      : '';
  }

  function renderBatchView() {
    // Button availability
    const daemonReady = state.daemon.status === 'ready';
    const running = state.batch.status === 'running' || state.batch.status === 'cancelling';
    const scanned = state.batch.scan.files;
    const filesToRun = state.batch.files.length > 0 ? state.batch.files : scanned;

    scanBtn.disabled = !daemonReady || running;
    startBtn.disabled = !daemonReady || running || (scanned.length === 0 && state.batch.files.length === 0);
    cancelBtn.disabled = !running;

    // Summary
    const s = state.batch;
    if (s.status === 'running' || s.status === 'cancelling') {
      batchSummary.textContent =
        `running · ${(s.currentFileIndex + 1)}/${s.files.length}`;
    } else if (s.status === 'complete' || s.status === 'failed' || s.status === 'cancelled') {
      batchSummary.textContent =
        `${s.status} · ${s.successful} ok / ${s.failed} failed · ${s.elapsed_s.toFixed(1)}s`;
    } else if (scanned.length > 0) {
      batchSummary.textContent = `${scanned.length} file(s) scanned`;
    } else {
      batchSummary.textContent = '';
    }

    // File rows. During a batch, render state.batch.files (live).
    // Before starting, render scanned files as pending rows.
    const rows = running || s.files.length > 0
      ? state.batch.files.map((f, i) => ({
          path: f.path,
          index: i,
          phase: f.phase,
          phase_progress: f.phase_progress ?? 0,
          completed_phases: f.completed_phases,
          status: f.status,
        }))
      : scanned.map((f, i) => ({
          path: f.path || f.name || '',
          index: i,
          phase: null,
          phase_progress: 0,
          completed_phases: [],
          status: 'pending',
        }));

    // Diff-free replace — few files, cheap enough to re-render.
    batchFilesEl.innerHTML = '';
    for (const row of rows) {
      const el = fileRowTmpl.content.firstElementChild.cloneNode(true);
      el.dataset.index = String(row.index);
      el.dataset.status = row.status || 'pending';
      el.querySelector('.file-name').textContent = basename(row.path);
      el.querySelector('.file-name').title = row.path;
      el.querySelector('.file-phase').textContent = row.phase
        ? `${row.phase} (${row.completed_phases.length}/10)`
        : '—';
      const bar = el.querySelector('.file-progress-bar');
      // Compute overall progress: completed/10 + (phase_progress / 10) of the current phase.
      const completed = row.completed_phases.length;
      const overall = Math.min(1, completed / 10 + (row.phase_progress || 0) / 10);
      bar.style.width = `${Math.round(overall * 100)}%`;
      el.querySelector('.file-progress-label').textContent = row.phase_progress > 0
        ? `${Math.round(row.phase_progress * 100)}%`
        : '';
      el.querySelector('.file-status').textContent = (row.status || 'pending').replace('_', ' ');
      batchFilesEl.appendChild(el);
    }
  }

  function basename(p) {
    if (!p) return '';
    const parts = String(p).split(/[\\/]/);
    return parts[parts.length - 1] || p;
  }

  // ── Event sources ──────────────────────────────────────────────────

  for (const tab of tabs) {
    tab.addEventListener('click', () => dispatch((s) => setView(s, tab.dataset.view)));
  }

  scanBtn.addEventListener('click', () => {
    const path = (scanPathInput.value || '').trim() || 'Material';
    window.vocality.send({
      cmd: 'scan_files',
      id: nextId('scan'),
      input_dir: path,
      probe_duration: false,
    });
  });

  startBtn.addEventListener('click', () => {
    const files = (state.batch.scan.files || [])
      .filter((f) => f.meta && f.meta.parse_ok !== false)
      .map((f) => f.path);
    window.vocality.send({
      cmd: 'process_batch',
      id: nextId('batch'),
      files,
      options: {},
    });
  });

  cancelBtn.addEventListener('click', () => {
    window.vocality.send({ cmd: 'cancel_batch', id: nextId('cancel') });
  });

  window.vocality.onStatus((status) => {
    dispatch((s) => ({ ...s, daemon: { ...s.daemon, status } }));
  });

  window.vocality.onEvent((event) => {
    dispatch((s) => reduceEvent(s, event));
  });

  // Initial status snapshot
  window.vocality.status().then((info) => {
    if (info && info.status) {
      dispatch((s) => ({
        ...s,
        daemon: {
          ...s.daemon,
          status: info.status,
          version: info.lastReady ? info.lastReady.engine_version : s.daemon.version,
          modelsLoaded: info.lastReady && info.lastReady.models_loaded
            ? info.lastReady.models_loaded.slice()
            : s.daemon.modelsLoaded,
        },
      }));
    }
  }).catch(() => { /* will catch up via onStatus */ });

  render();
})();
