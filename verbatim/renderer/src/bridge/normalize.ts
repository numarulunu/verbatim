import type { Collision, DaemonStatus, FileItem, Person } from '../types';

export interface RendererSettings {
  hf: string;
  anth: string;
  defInput: string;
  defOutput: string;
  model: string;
  lang: string;
  polish: string;
  dataDir: string;
}

export interface StoredSettings {
  hf_token?: string;
  anthropic_api_key?: string;
  data_dir?: string;
  default_input?: string;
  default_output?: string;
  whisper_model?: string;
  language?: string;
  polish?: string;
  huggingface_token?: string;
  hf?: string;
  anth?: string;
  defInput?: string;
  defOutput?: string;
  model?: string;
  lang?: string;
  dataDir?: string;
}

export interface StatusEnvelope {
  status: DaemonStatus;
  lastReady: Record<string, unknown> | null;
  lastExit: {
    code: number | null;
    signal: string | null;
    message?: string;
  } | null;
}

export interface ResourceStatsEvent {
  type: 'resource_stats';
  cpu_pct: number;
  gpu_pct: number;
  gpu_mem_used_gb: number;
  gpu_mem_total_gb: number;
  ram_used_gb: number;
  ram_total_gb: number;
  disk_free_gb: number;
}

export interface PhaseProgressEvent {
  type: 'phase_progress';
  file_index: number;
  path?: string;
  phase: string;
  phaseIndex: number;
  phase_progress: number;
}

export interface BatchStartedEvent {
  type: 'batch_started';
  total: number;
}

export interface FileStartedEvent {
  type: 'file_started';
  file_index: number;
  path: string;
}

export interface FilesScannedEvent {
  type: 'files_scanned';
  files: FileItem[];
}

export interface PhaseStartedEvent {
  type: 'phase_started';
  file_index: number;
  path?: string;
  phase: string;
  phaseIndex: number;
}

export interface PhaseCompleteEvent {
  type: 'phase_complete';
  file_index: number;
  path?: string;
  phase: string;
  phaseIndex: number;
}

export interface FileCompleteEvent {
  type: 'file_complete';
  file_index: number;
  path?: string;
  state: 'success' | 'failed';
  output_path?: string;
}

export interface BatchCompleteEvent {
  type: 'batch_complete';
  total_files: number;
  successful: number;
  failed: number;
  total_elapsed_s?: number;
  failures?: Array<Record<string, unknown>>;
}

export interface PersonsListedEvent {
  type: 'persons_listed';
  persons: Person[];
}

export interface PersonInspectedEvent {
  type: 'person_inspected';
  person: Person;
}

export interface PersonRenamedEvent {
  type: 'person_renamed';
  old_id: string;
  new_id: string;
}

export interface PersonMergedEvent {
  type: 'person_merged';
  source_id: string;
  target_id: string;
}

export interface CollisionDetectedEvent {
  type: 'collision_detected';
  pair: [string, string];
  cosine: number;
}

export interface CorpusSummaryEvent {
  type: 'corpus_summary';
  session_count: number;
  persons: Record<string, unknown>;
  total_hours: number;
}

export interface CancelAcceptedEvent {
  type: 'cancel_accepted';
}

export interface ToastEvent {
  type: 'error' | 'warning';
  title: string;
  body?: string;
  file?: string;
  stderr_tail?: string;
}

export type NormalizedEvent =
  | ResourceStatsEvent
  | FilesScannedEvent
  | BatchStartedEvent
  | FileStartedEvent
  | PhaseStartedEvent
  | PhaseProgressEvent
  | PhaseCompleteEvent
  | FileCompleteEvent
  | BatchCompleteEvent
  | PersonsListedEvent
  | PersonInspectedEvent
  | PersonRenamedEvent
  | PersonMergedEvent
  | CollisionDetectedEvent
  | CorpusSummaryEvent
  | CancelAcceptedEvent
  | ToastEvent;

export const DEFAULT_RENDERER_SETTINGS: RendererSettings = {
  hf: '',
  anth: '',
  defInput: '',
  defOutput: '',
  model: 'large-v3-turbo',
  lang: 'auto',
  polish: 'cli',
  dataDir: '~/.verbatim',
};

const VALID_STATUS = new Set<DaemonStatus>(['down', 'spawning', 'ready', 'busy', 'shutting_down', 'crashed']);
const PHASE_ORDER = new Map([
  ['isolation', 0],
  ['vad', 1],
  ['decode', 2],
  ['asr', 3],
  ['alignment', 4],
  ['diarization', 5],
  ['identification', 6],
  ['verification', 7],
  ['polish', 8],
  ['corpus_update', 9],
]);

function readString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function readNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function readArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function readStringArray(value: unknown): string[] {
  return readArray(value).flatMap((item) => (typeof item === 'string' ? [item] : []));
}

function readObject(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : undefined;
}

function pickString(raw: StoredSettings | null | undefined, keys: string[], fallback: string): string {
  if (raw && typeof raw === 'object') {
    for (const key of keys) {
      const value = readString(raw[key as keyof StoredSettings]);
      if (value !== undefined) return value;
    }
  }
  return fallback;
}

function pickBody(raw: Record<string, unknown>): string | undefined {
  const direct = readString(raw.body);
  if (direct !== undefined) return direct;

  const context = raw.context;
  if (typeof context === 'string') return context;
  if (typeof context === 'number' || typeof context === 'boolean') return String(context);
  if (context && typeof context === 'object') {
    try {
      return JSON.stringify(context);
    } catch {
      return undefined;
    }
  }

  return readString(raw.file);
}

function readBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
}

function basename(filePath: string): string {
  const parts = filePath.split(/[\\/]/);
  return parts[parts.length - 1] || filePath;
}

function normalizeParseStatus(meta: unknown): FileItem['parseStatus'] {
  if (!meta || typeof meta !== 'object') {
    return 'ok';
  }

  const record = meta as Record<string, unknown>;
  if (readBoolean(record.parse_ok) === false) {
    return 'unreadable';
  }
  if (readBoolean(record.parse_partial) === true) {
    return 'partial';
  }
  return 'ok';
}

function normalizeScannedFiles(files: unknown): FileItem[] {
  if (!Array.isArray(files)) {
    return [];
  }

  return files.flatMap((entry) => {
    if (!entry || typeof entry !== 'object') {
      return [];
    }

    const record = entry as Record<string, unknown>;
    const filePath = readString(record.path);
    if (!filePath) {
      return [];
    }

    return [{
      path: filePath,
      name: basename(filePath),
      duration: readNumber(record.duration_s ?? record.duration) ?? 0,
      size: readNumber(record.size_bytes ?? record.size ?? record.bytes) ?? 0,
      alreadyProcessed: readBoolean(record.already_processed) ?? false,
      parseStatus: normalizeParseStatus(record.meta),
    }];
  });
}

function clamp01(value: number): number {
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

function getPhaseIndex(phase: string, fallback: unknown): number {
  const mapped = PHASE_ORDER.get(phase);
  if (mapped !== undefined) return mapped;
  return readNumber(fallback) ?? 0;
}

function readVoiceprintFiles(value: unknown): { name: string; bytes: number }[] {
  return readArray(value).flatMap((item, index) => {
    if (typeof item === 'string') {
      return [{ name: basename(item), bytes: 0 }];
    }

    const record = readObject(item);
    if (!record) {
      return [];
    }

    const name = readString(record.name) ?? readString(record.path) ?? readString(record.file) ?? `voiceprint-${index + 1}`;
    return [{
      name: basename(name),
      bytes: readNumber(record.bytes ?? record.size ?? record.size_bytes) ?? 0,
    }];
  });
}

function normalizePerson(raw: unknown, voiceprintFiles?: unknown): Person | null {
  const record = readObject(raw);
  if (!record) {
    return null;
  }

  const id = readString(record.id) ?? readString(record.person_id) ?? '';
  if (!id) {
    return null;
  }

  const displayName = readString(record.displayName)
    ?? readString(record.display_name)
    ?? readString(record.name)
    ?? id;

  const role = readString(record.default_role ?? record.role);
  const normalizedRole: Person['role'] = role === 'teacher' || role === 'student' ? role : 'unknown';

  return {
    id,
    displayName,
    role: normalizedRole,
    sessionsTeacher:
      readNumber(record.sessionsTeacher ?? record.sessions_teacher ?? record.n_sessions_as_teacher) ?? 0,
    sessionsStudent:
      readNumber(record.sessionsStudent ?? record.sessions_student ?? record.n_sessions_as_student) ?? 0,
    totalHours: readNumber(record.totalHours ?? record.total_hours) ?? 0,
    voiceType: readString(record.voiceType ?? record.voice_type),
    fach: readString(record.fach),
    firstSeen: readString(record.firstSeen ?? record.first_seen) ?? '',
    lastUpdated: readString(record.lastUpdated ?? record.last_updated) ?? '',
    observedRegions: readStringArray(record.observedRegions ?? record.observed_regions),
    bootstrapCounter:
      readNumber(record.bootstrapCounter ?? record.bootstrap_counter ?? record.bootstrap_sessions_remaining) ?? 0,
    voiceprintFiles: readVoiceprintFiles(voiceprintFiles ?? record.voiceprintFiles ?? record.voiceprint_files),
  };
}

export function normalizeSettings(raw: StoredSettings | null | undefined): RendererSettings {
  return {
    hf: pickString(raw, ['hf', 'hf_token', 'huggingface_token'], DEFAULT_RENDERER_SETTINGS.hf),
    anth: pickString(raw, ['anth', 'anthropic_api_key'], DEFAULT_RENDERER_SETTINGS.anth),
    defInput: pickString(raw, ['defInput', 'default_input'], DEFAULT_RENDERER_SETTINGS.defInput),
    defOutput: pickString(raw, ['defOutput', 'default_output'], DEFAULT_RENDERER_SETTINGS.defOutput),
    model: pickString(raw, ['model', 'whisper_model'], DEFAULT_RENDERER_SETTINGS.model),
    lang: pickString(raw, ['lang', 'language'], DEFAULT_RENDERER_SETTINGS.lang),
    polish: pickString(raw, ['polish'], DEFAULT_RENDERER_SETTINGS.polish),
    dataDir: pickString(raw, ['dataDir', 'data_dir'], DEFAULT_RENDERER_SETTINGS.dataDir),
  };
}

export function encodeSettings(settings: Partial<RendererSettings>): StoredSettings {
  return {
    hf_token: (settings.hf ?? '').trim(),
    anthropic_api_key: (settings.anth ?? '').trim(),
    default_input: (settings.defInput ?? '').trim(),
    default_output: (settings.defOutput ?? '').trim(),
    whisper_model: (settings.model ?? DEFAULT_RENDERER_SETTINGS.model).trim(),
    language: (settings.lang ?? DEFAULT_RENDERER_SETTINGS.lang).trim(),
    polish: (settings.polish ?? DEFAULT_RENDERER_SETTINGS.polish).trim(),
    data_dir: (settings.dataDir ?? DEFAULT_RENDERER_SETTINGS.dataDir).trim(),
  };
}

export function normalizeStatus(raw: unknown): DaemonStatus {
  if (typeof raw === 'string' && VALID_STATUS.has(raw as DaemonStatus)) {
    return raw as DaemonStatus;
  }

  if (raw && typeof raw === 'object') {
    const status = readString((raw as { status?: unknown }).status);
    if (status && VALID_STATUS.has(status as DaemonStatus)) {
      return status as DaemonStatus;
    }
  }

  return 'down';
}

export function normalizeDaemonEvent(raw: unknown): NormalizedEvent | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }

  const event = raw as Record<string, unknown>;
  const type = readString(event.type);

  if (type === 'resource_stats') {
    return {
      type: 'resource_stats',
      cpu_pct: readNumber(event.cpu_pct) ?? 0,
      gpu_pct: readNumber(event.gpu_pct) ?? 0,
      gpu_mem_used_gb: readNumber(event.gpu_mem_used_gb) ?? 0,
      gpu_mem_total_gb: readNumber(event.gpu_mem_total_gb) ?? 0,
      ram_used_gb: readNumber(event.ram_used_gb) ?? 0,
      ram_total_gb: readNumber(event.ram_total_gb) ?? 0,
      disk_free_gb: readNumber(event.disk_free_gb) ?? 0,
    };
  }

  if (type === 'files_scanned') {
    return {
      type: 'files_scanned',
      files: normalizeScannedFiles(event.files),
    };
  }

  if (type === 'phase_progress') {
    const phase = readString(event.phase) ?? '';
    return {
      type: 'phase_progress',
      file_index: readNumber(event.file_index ?? event.index) ?? 0,
      phase,
      phaseIndex: getPhaseIndex(phase, event.phase_index),
      phase_progress: clamp01(readNumber(event.phase_progress ?? event.progress) ?? 0),
    };
  }

  if (type === 'batch_started') {
    return {
      type: 'batch_started',
      total: readNumber(event.file_count ?? event.total) ?? 0,
    };
  }

  if (type === 'file_started') {
    return {
      type: 'file_started',
      file_index: readNumber(event.index ?? event.file_index) ?? 0,
      path: readString(event.file) ?? readString(event.path) ?? '',
    };
  }

  if (type === 'phase_started') {
    const phase = readString(event.phase) ?? '';
    return {
      type: 'phase_started',
      file_index: readNumber(event.file_index ?? event.index) ?? 0,
      phase,
      phaseIndex: getPhaseIndex(phase, event.phase_index),
    };
  }

  if (type === 'phase_complete') {
    const phase = readString(event.phase) ?? '';
    return {
      type: 'phase_complete',
      file_index: readNumber(event.file_index ?? event.index) ?? 0,
      phase,
      phaseIndex: getPhaseIndex(phase, event.phase_index),
    };
  }

  if (type === 'file_complete') {
    return {
      type: 'file_complete',
      file_index: readNumber(event.file_index ?? event.index) ?? 0,
      state: readString(event.state) === 'failed' ? 'failed' : 'success',
      output_path: readString(event.output_path),
    };
  }

  if (type === 'batch_complete') {
    return {
      type: 'batch_complete',
      total_files: readNumber(event.total_files) ?? 0,
      successful: readNumber(event.successful) ?? 0,
      failed: readNumber(event.failed) ?? 0,
      total_elapsed_s: readNumber(event.total_elapsed_s),
      failures: readArray(event.failures).flatMap((failure) => {
        const record = readObject(failure);
        return record ? [record] : [];
      }),
    };
  }

  if (type === 'persons_listed') {
    return {
      type: 'persons_listed',
      persons: readArray(event.persons).flatMap((person) => {
        const normalized = normalizePerson(person);
        return normalized ? [normalized] : [];
      }),
    };
  }

  if (type === 'person_inspected') {
    const person = normalizePerson(event.person, event.voiceprint_files);
    if (!person) {
      return null;
    }

    return {
      type: 'person_inspected',
      person,
    };
  }

  if (type === 'person_renamed') {
    return {
      type: 'person_renamed',
      old_id: readString(event.old_id) ?? '',
      new_id: readString(event.new_id) ?? '',
    };
  }

  if (type === 'person_merged') {
    return {
      type: 'person_merged',
      source_id: readString(event.source_id) ?? '',
      target_id: readString(event.target_id) ?? '',
    };
  }

  if (type === 'collision_detected') {
    const pair = readStringArray(event.pair);
    return {
      type: 'collision_detected',
      pair: [pair[0] ?? '', pair[1] ?? ''],
      cosine: readNumber(event.cosine) ?? 0,
    };
  }

  if (type === 'corpus_summary') {
    return {
      type: 'corpus_summary',
      session_count: readNumber(event.session_count) ?? 0,
      persons: readObject(event.persons) ?? {},
      total_hours: readNumber(event.total_hours) ?? 0,
    };
  }

  if (type === 'cancel_accepted') {
    return { type: 'cancel_accepted' };
  }

  if (type === 'error' || type === 'warning') {
    const title =
      readString(event.title) ??
      readString(event.message) ??
      readString(event.error_type) ??
      readString(event.warning_type) ??
      (type === 'error' ? 'Error' : 'Warning');

    return {
      type,
      title,
      body: pickBody(event),
      file: readString(event.file),
      stderr_tail: readString(event.stderr_tail),
    };
  }

  return null;
}
