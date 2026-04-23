import { encodeRendererCommand, type RendererCommand } from './commands';
import {
  DEFAULT_RENDERER_SETTINGS,
  encodeSettings,
  normalizeDaemonEvent,
  normalizeSettings,
  normalizeStatus,
  type NormalizedEvent,
  type RendererSettings,
  type StatusEnvelope,
} from './normalize';
import { createBatchPathState } from './batchPathState';
import type { UpdateStatus } from '../types';

const MISSING_BRIDGE_MESSAGE = 'Verbatim bridge unavailable. The preload script may have failed to initialize.';

function missingBridgeError(): Error {
  return new Error(MISSING_BRIDGE_MESSAGE);
}

function createFallbackApi() {
  return {
    minimizeWindow: (): Promise<{ maximized: boolean }> => Promise.resolve({ maximized: false }),
    toggleMaximizeWindow: (): Promise<{ maximized: boolean }> => Promise.resolve({ maximized: false }),
    closeWindow: (): Promise<{ maximized: boolean }> => Promise.resolve({ maximized: false }),
    send: () => Promise.reject(missingBridgeError()),
    onEvent: () => () => {},
    onStatus: () => () => {},
    status: (): Promise<StatusEnvelope> => Promise.resolve({
      status: 'down',
      lastReady: null,
      lastExit: null,
    }),
    restart: () => Promise.reject(missingBridgeError()),
    pickFolder: (): Promise<string | null> => Promise.resolve(null),
    openPath: (): Promise<{ ok: boolean; error: string | null }> => Promise.reject(missingBridgeError()),
    getSettings: () => Promise.resolve(DEFAULT_RENDERER_SETTINGS),
    saveSettings: () => Promise.reject(missingBridgeError()),
    updateStatus: (): Promise<UpdateStatus | null> => Promise.resolve(null),
    onUpdateStatus: () => () => {},
  };
}

const api = window.verbatim ?? createFallbackApi();
const batchPathState = createBatchPathState();

function resolveBatchPath(fileIndex: number, fallback?: string): string {
  return batchPathState.resolve(fileIndex, fallback);
}

export const verbatimClient = {
  minimizeWindow() {
    return api.minimizeWindow();
  },

  toggleMaximizeWindow() {
    return api.toggleMaximizeWindow();
  },

  closeWindow() {
    return api.closeWindow();
  },

  send(command: RendererCommand) {
    const encoded = encodeRendererCommand(command);
    if (encoded.cmd === 'process_batch') {
      batchPathState.queue(
        Array.isArray(encoded.files)
          ? encoded.files.filter((file): file is string => typeof file === 'string')
          : [],
      );
    }
    return api.send(encoded).catch((error) => {
      if (encoded.cmd === 'process_batch') {
        batchPathState.cancelPending();
      }
      throw error;
    });
  },

  listPersons() {
    return api.send({ cmd: 'list_persons' });
  },

  inspectPerson(personId: string) {
    return api.send({ cmd: 'inspect_person', person_id: personId });
  },

  editPerson(personId: string, updates: Record<string, unknown>) {
    return api.send({ cmd: 'edit_person', person_id: personId, updates });
  },

  renamePerson(oldId: string, newId: string) {
    return api.send({ cmd: 'rename_person', old_id: oldId, new_id: newId });
  },

  mergePersons(sourceId: string, targetId: string) {
    return api.send({ cmd: 'merge_persons', source_id: sourceId, target_id: targetId });
  },

  redoBatch(filter: Record<string, unknown>) {
    return api.send({ cmd: 'redo_batch', filter });
  },

  getCorpusSummary() {
    return api.send({ cmd: 'get_corpus_summary' });
  },

  onEvent(cb: (event: NormalizedEvent) => void) {
    return api.onEvent((event) => {
      const normalized = normalizeDaemonEvent(event);
      if (normalized) {
        if (normalized.type === 'batch_complete' || normalized.type === 'cancel_accepted') {
          batchPathState.clear();
        }

        if (normalized.type === 'batch_started') {
          batchPathState.confirm();
        }

        if (normalized.type === 'file_started') {
          cb({ ...normalized, path: resolveBatchPath(normalized.file_index, normalized.path) });
          return;
        }

        if (
          normalized.type === 'phase_started' ||
          normalized.type === 'phase_progress' ||
          normalized.type === 'phase_complete' ||
          normalized.type === 'file_complete'
        ) {
          cb({ ...normalized, path: resolveBatchPath(normalized.file_index) } as NormalizedEvent);
          return;
        }

        cb(normalized);
      }
    });
  },

  onStatus(cb: (status: ReturnType<typeof normalizeStatus>) => void) {
    return api.onStatus((status) => cb(normalizeStatus(status)));
  },

  status() {
    return api.status().then(normalizeStatus);
  },

  restart() {
    return api.restart();
  },

  pickFolder(defaultPath?: string) {
    return api.pickFolder(defaultPath);
  },

  openPath(targetPath: string) {
    return api.openPath(targetPath);
  },

  getSettings() {
    return api.getSettings().then(normalizeSettings);
  },

  saveSettings(settings: Partial<RendererSettings>) {
    return api.saveSettings(encodeSettings(settings) as Record<string, unknown>);
  },

  updateStatus(): Promise<UpdateStatus | null> {
    return api.updateStatus();
  },

  onUpdateStatus(cb: (event: unknown) => void) {
    return api.onUpdateStatus(cb);
  },
};

export type VerbatimClient = typeof verbatimClient;
