/**
 * Vocality renderer — Gate 6C shell.
 *
 * Owns the reducer loop: events from the main-process daemon come in via
 * window.vocality.onEvent, UI actions (tab clicks) flow through setView.
 * A single render(state) pass updates the DOM.
 *
 * The views themselves (Batch / Registry / Redo body content) are
 * placeholders in this gate — 6D/E/F fill them in.
 */
'use strict';

(() => {
  if (!window.vocality) {
    document.body.innerHTML =
      '<main style="padding:24px;color:#f7768e">ERROR: preload not wired — window.vocality is missing.</main>';
    return;
  }

  // Lightweight reducer + state container. Mirrors the pattern the
  // app-state tests use (initialState + reduceEvent + setView), re-
  // implemented in-line because the renderer can't `require` Node-side
  // modules through the context bridge.
  let state = initialState();

  function initialState() {
    return {
      view: 'batch',
      daemon: { status: 'down', version: null },
      errors: [],
    };
  }

  function dispatch(mutator) {
    state = mutator(state);
    render();
  }

  // ── Rendering ──────────────────────────────────────────────────────

  const statusDot = document.querySelector('.status-dot');
  const statusLabel = document.querySelector('.status-label');
  const statusVersion = document.querySelector('.status-version');
  const statusLastError = document.querySelector('.status-last-error');
  const tabs = Array.from(document.querySelectorAll('.tab'));
  const views = Array.from(document.querySelectorAll('.view'));

  function render() {
    // Tabs
    for (const tab of tabs) {
      const isActive = tab.dataset.view === state.view;
      tab.classList.toggle('active', isActive);
      tab.setAttribute('aria-selected', String(isActive));
    }
    // Views
    for (const v of views) {
      v.hidden = v.dataset.view !== state.view;
    }
    // Status bar
    statusDot.dataset.status = state.daemon.status;
    statusLabel.textContent = `daemon: ${state.daemon.status}`;
    statusVersion.textContent = state.daemon.version ? `v${state.daemon.version}` : '';
    const lastError = state.errors[state.errors.length - 1];
    statusLastError.textContent = lastError
      ? `${lastError.error_type}: ${lastError.message}`
      : '';
  }

  // ── Wiring ─────────────────────────────────────────────────────────

  for (const tab of tabs) {
    tab.addEventListener('click', () => {
      dispatch((s) => ({ ...s, view: tab.dataset.view }));
    });
  }

  window.vocality.onStatus((status) => {
    dispatch((s) => ({ ...s, daemon: { ...s.daemon, status } }));
  });

  window.vocality.onEvent((event) => {
    dispatch((s) => {
      if (event.type === 'ready') {
        return { ...s, daemon: { ...s.daemon, status: 'ready', version: event.engine_version || null } };
      }
      if (event.type === 'shutting_down') {
        return { ...s, daemon: { ...s.daemon, status: 'down' } };
      }
      if (event.type === 'error') {
        const next = s.errors.concat(event);
        if (next.length > 20) next.shift();
        return { ...s, errors: next };
      }
      return s;
    });
  });

  // Pull the current status once on startup in case events were emitted
  // before the renderer subscribed.
  window.vocality.status().then((info) => {
    if (info && info.status) {
      dispatch((s) => ({
        ...s,
        daemon: {
          ...s.daemon,
          status: info.status,
          version: info.lastReady ? info.lastReady.engine_version : s.daemon.version,
        },
      }));
    }
  }).catch(() => { /* main may not be ready yet; next onStatus will catch up */ });

  render();
})();
