/**
 * app-state — pure state reducer for the renderer.
 *
 * Events come in, a new state goes out. DOM updates read from state. No
 * DOM references here, so this module is unit-testable via `node --test`
 * without Electron.
 *
 * Immutability convention: reducers always return a new object; they
 * never mutate the input. This keeps state transitions traceable.
 */
'use strict';

const ERROR_LOG_CAP = 50;
const WARNING_LOG_CAP = 50;
const PHASE_COUNT = 10;

/**
 * Initial state shape.
 */
function initialState() {
  return {
    view: 'batch',       // 'batch' | 'registry' | 'redo'
    batch: {
      files: [],         // [{ path, file_id?, status, phase?, phase_index?, phase_progress?, completed_phases, output_path?, error?, stats? }]
      status: 'idle',    // 'idle' | 'running' | 'cancelling' | 'complete' | 'failed'
      currentFileIndex: -1,
      startedAt: null,
      elapsed_s: 0,
      successful: 0,
      failed: 0,
      scan: { files: [] }, // last files_scanned result
    },
    registry: {
      persons: [],       // [{id, display_name, default_role, ...}]
      collisions: [],    // [{pair: [a, b], cosine}]
      activeInspect: null,      // last PersonInspectedEvent payload
      lastRename: null,
      lastMerge: null,
    },
    redo: {
      filter: { threshold: 3 },
      candidates: [],
    },
    corpus: {
      session_count: 0,
      persons: {},
      total_hours: 0,
    },
    daemon: {
      status: 'down',    // 'down' | 'spawning' | 'ready' | 'busy' | 'shutting_down' | 'crashed'
      version: null,
      modelsLoaded: [],
      systemInfo: null,  // last SystemInfoEvent payload
    },
    errors: [],          // [{...ErrorEvent}], capped at ERROR_LOG_CAP
    warnings: [],        // [{...WarningEvent}], capped at WARNING_LOG_CAP
  };
}

function _ensureFileSlot(files, index, path) {
  const next = files.slice();
  while (next.length <= index) {
    next.push({
      path: '',
      status: 'pending',
      completed_phases: [],
    });
  }
  if (path && !next[index].path) {
    next[index] = { ...next[index], path };
  }
  return next;
}

function _updateFileAt(files, index, patch) {
  const next = files.slice();
  const existing = next[index] || { path: '', status: 'pending', completed_phases: [] };
  next[index] = { ...existing, ...patch };
  return next;
}

function _appendCapped(list, entry, cap) {
  if (list.length >= cap) {
    return list.slice(-cap + 1).concat(entry);
  }
  return list.concat(entry);
}

/**
 * Pure event reducer. Returns a NEW state; never mutates the input.
 */
function reduceEvent(state, event) {
  if (!event || typeof event.type !== 'string') return state;

  switch (event.type) {
    // ── Lifecycle ────────────────────────────────────────────────────────
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
      return { ...state, daemon: { ...state.daemon, status: 'down' } };

    case 'pong':
      return state; // correlation-only; callers filter by id

    case 'cancel_accepted':
      return {
        ...state,
        batch: { ...state.batch, status: state.batch.status === 'running' ? 'cancelling' : state.batch.status },
      };

    // ── Detect ───────────────────────────────────────────────────────────
    case 'system_info':
      return {
        ...state,
        daemon: { ...state.daemon, systemInfo: { ...event } },
      };

    // ── Person management ────────────────────────────────────────────────
    case 'persons_listed':
      return {
        ...state,
        registry: {
          ...state.registry,
          persons: Array.isArray(event.persons) ? event.persons.slice() : [],
        },
      };

    case 'person_registered': {
      const existing = state.registry.persons.filter((p) => p.id !== event.person_id);
      return {
        ...state,
        registry: {
          ...state.registry,
          persons: existing.concat(event.record || { id: event.person_id }),
        },
      };
    }

    case 'person_inspected':
      return {
        ...state,
        registry: { ...state.registry, activeInspect: { ...event } },
      };

    case 'person_renamed': {
      const persons = state.registry.persons.map((p) =>
        p.id === event.old_id ? { ...p, id: event.new_id } : p,
      );
      return {
        ...state,
        registry: {
          ...state.registry,
          persons,
          lastRename: { old_id: event.old_id, new_id: event.new_id },
        },
      };
    }

    case 'person_merged': {
      const persons = state.registry.persons.filter((p) => p.id !== event.source_id);
      return {
        ...state,
        registry: {
          ...state.registry,
          persons,
          lastMerge: { source_id: event.source_id, target_id: event.target_id },
        },
      };
    }

    case 'collision_detected':
      return {
        ...state,
        registry: {
          ...state.registry,
          collisions: state.registry.collisions.concat({
            pair: Array.isArray(event.pair) ? event.pair.slice() : [],
            cosine: event.cosine ?? 0,
          }),
        },
      };

    // ── Scan ─────────────────────────────────────────────────────────────
    case 'files_scanned':
      return {
        ...state,
        batch: {
          ...state.batch,
          scan: { files: Array.isArray(event.files) ? event.files.slice() : [] },
        },
      };

    // ── Batch lifecycle ──────────────────────────────────────────────────
    case 'batch_started':
      return {
        ...state,
        batch: {
          ...state.batch,
          files: [],
          status: 'running',
          currentFileIndex: -1,
          startedAt: event.timestamp || new Date().toISOString(),
          elapsed_s: 0,
          successful: 0,
          failed: 0,
        },
      };

    case 'file_started': {
      const files = _ensureFileSlot(state.batch.files, event.index ?? 0, event.file || '');
      const patched = _updateFileAt(files, event.index ?? 0, {
        status: 'running',
        phase: null,
        phase_index: null,
        phase_progress: 0,
      });
      return {
        ...state,
        batch: { ...state.batch, files: patched, currentFileIndex: event.index ?? 0 },
      };
    }

    case 'phase_started': {
      const i = event.file_index ?? 0;
      const files = _ensureFileSlot(state.batch.files, i);
      const patched = _updateFileAt(files, i, {
        phase: event.phase,
        phase_index: event.phase_index ?? null,
        phase_progress: 0,
      });
      return { ...state, batch: { ...state.batch, files: patched } };
    }

    case 'phase_progress': {
      const i = event.file_index ?? 0;
      const files = _ensureFileSlot(state.batch.files, i);
      const patched = _updateFileAt(files, i, {
        phase: event.phase,
        phase_progress: Math.max(0, Math.min(1, Number(event.phase_progress) || 0)),
      });
      return { ...state, batch: { ...state.batch, files: patched } };
    }

    case 'phase_complete': {
      const i = event.file_index ?? 0;
      const files = _ensureFileSlot(state.batch.files, i);
      const existing = files[i];
      const completed = existing.completed_phases.includes(event.phase)
        ? existing.completed_phases
        : existing.completed_phases.concat(event.phase);
      const patched = _updateFileAt(files, i, {
        phase_progress: 1,
        completed_phases: completed,
      });
      return { ...state, batch: { ...state.batch, files: patched } };
    }

    case 'file_complete': {
      const i = event.file_index ?? 0;
      const files = _ensureFileSlot(state.batch.files, i);
      const ok = event.stats && event.stats.ok === true;
      const patched = _updateFileAt(files, i, {
        status: ok ? 'complete' : 'failed',
        output_path: event.output_path || '',
        stats: event.stats || {},
      });
      return { ...state, batch: { ...state.batch, files: patched } };
    }

    case 'batch_complete': {
      const failedCandidate = state.batch.status === 'cancelling' ? 'cancelled' : 'complete';
      return {
        ...state,
        batch: {
          ...state.batch,
          status: (event.failed ?? 0) > 0 && (event.successful ?? 0) === 0 ? 'failed' : failedCandidate,
          successful: event.successful ?? 0,
          failed: event.failed ?? 0,
          elapsed_s: event.total_elapsed_s ?? 0,
        },
      };
    }

    // ── Corpus ───────────────────────────────────────────────────────────
    case 'corpus_summary':
      return {
        ...state,
        corpus: {
          session_count: event.session_count ?? 0,
          persons: event.persons || {},
          total_hours: event.total_hours ?? 0,
        },
      };

    // ── Diagnostics ──────────────────────────────────────────────────────
    case 'error':
      return {
        ...state,
        errors: _appendCapped(state.errors, { ...event }, ERROR_LOG_CAP),
      };

    case 'warning':
      return {
        ...state,
        warnings: _appendCapped(state.warnings, { ...event }, WARNING_LOG_CAP),
      };

    default:
      return state;
  }
}

/**
 * UI-only reducer: switch the visible view. Not an ipc_protocol event —
 * triggered by clicks on the tab bar.
 */
function setView(state, view) {
  if (!['batch', 'registry', 'redo'].includes(view)) return state;
  if (state.view === view) return state;
  return { ...state, view };
}

// Dual-mode: Node CommonJS (tests) + browser global (renderer via <script>).
const __exports = { initialState, reduceEvent, setView, ERROR_LOG_CAP, WARNING_LOG_CAP, PHASE_COUNT };
if (typeof module !== 'undefined' && module.exports) {
  module.exports = __exports;
} else if (typeof window !== 'undefined') {
  window.appState = __exports;
}
