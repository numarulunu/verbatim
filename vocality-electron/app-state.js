/**
 * app-state — pure state reducer for the renderer.
 *
 * Same pattern as the converter: events come in, state goes out, DOM updates
 * read from state. No DOM references here, so this module is unit-testable
 * via `node --test` without Electron.
 *
 * GATE-3 SCAFFOLD. Only the lifecycle events (`ready`, `shutting_down`) are
 * handled today. Gate 6 fills in reducers for every event type defined in
 * `ipc_protocol.py`: batch_started, file_started, phase_* , file_complete,
 * batch_complete, error, warning, persons_listed, etc.
 */
'use strict';

/**
 * Initial state shape. Gate 6 extends this with progress tracking, registry
 * snapshots, redo filter state, and settings.
 */
function initialState() {
  return {
    view: 'batch',       // 'batch' | 'registry' | 'redo'
    batch: {
      files: [],         // [{path, file_id, status, phase?, phase_progress?}]
      status: 'idle',    // 'idle' | 'running' | 'cancelled' | 'complete'
      currentFileIndex: -1,
      startedAt: null,
      elapsed_s: 0,
    },
    registry: {
      persons: [],       // [{id, display_name, role, sessions, ...}]
      collisions: [],    // [{pair: [a, b], cosine}]
    },
    redo: {
      filter: { threshold: 3 },
      candidates: [],
    },
    daemon: {
      status: 'down',    // 'down' | 'spawning' | 'ready' | 'busy' | 'shutting_down'
      version: null,
      modelsLoaded: [],
    },
    errors: [],          // last N error events for the status bar
  };
}

/**
 * Pure event reducer. Returns a NEW state; never mutates the input.
 */
function reduceEvent(state, event) {
  switch (event.type) {
    case 'ready':
      return {
        ...state,
        daemon: {
          ...state.daemon,
          status: 'ready',
          version: event.engine_version ?? null,
          modelsLoaded: Array.isArray(event.models_loaded) ? event.models_loaded.slice() : [],
        },
      };

    case 'shutting_down':
      return {
        ...state,
        daemon: { ...state.daemon, status: 'down' },
      };

    // Gate 6 adds: batch_started, file_started, phase_started, phase_progress,
    // phase_complete, file_complete, batch_complete, error, warning,
    // persons_listed, person_registered, person_inspected, collision_detected,
    // cancel_accepted, corpus_summary, files_scanned.

    default:
      return state;
  }
}

module.exports = { initialState, reduceEvent };
