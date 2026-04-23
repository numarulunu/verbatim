export type DaemonStatus =
  | 'down'
  | 'spawning'
  | 'ready'
  | 'busy'
  | 'shutting_down'
  | 'crashed';

export type PhaseName =
  | 'isolation'
  | 'vad'
  | 'decode'
  | 'asr'
  | 'alignment'
  | 'diarization'
  | 'identification'
  | 'verification'
  | 'polish'
  | 'corpus_update';

export const PHASES: PhaseName[] = [
  'isolation',
  'vad',
  'decode',
  'asr',
  'alignment',
  'diarization',
  'identification',
  'verification',
  'polish',
  'corpus_update',
];

export const PHASE_LABELS: Record<PhaseName, string> = {
  isolation: 'Isolation',
  decode: 'Decode',
  vad: 'VAD',
  asr: 'ASR',
  alignment: 'Align',
  diarization: 'Diarize',
  identification: 'Identify',
  verification: 'Verify',
  polish: 'Polish',
  corpus_update: 'Corpus',
};

export interface FileItem {
  path: string;
  name: string;
  duration: number;
  size: number;
  alreadyProcessed?: boolean;
  parseStatus?: 'ok' | 'partial' | 'unreadable';
}

export type FileState =
  | 'idle'
  | 'queued'
  | 'running'
  | 'success'
  | 'failed'
  | 'skipped';

export interface FileProgress {
  currentPhase?: PhaseName;
  currentPhaseIndex: number; // 0..9
  phaseProgress: number; // 0..1 for current phase
  completedPhases: PhaseName[];
  state: FileState;
  startedAt?: number;
  endedAt?: number;
  errorMessage?: string;
}

export interface Person {
  id: string;
  displayName: string;
  role: 'teacher' | 'student' | 'unknown';
  sessionsTeacher: number;
  sessionsStudent: number;
  totalHours: number;
  voiceType?: string;
  fach?: string;
  firstSeen: string;
  lastUpdated: string;
  observedRegions: string[];
  bootstrapCounter: number;
  voiceprintFiles: { name: string; bytes: number }[];
}

export interface Collision {
  a: string;
  b: string;
  similarity: number;
}

export interface ResourceStats {
  cpu_pct: number;
  gpu_pct: number;
  gpu_mem_used_gb: number;
  gpu_mem_total_gb: number;
  ram_used_gb: number;
  ram_total_gb: number;
  disk_free_gb: number;
}

export type UpdateStatusKind = 'checking' | 'current' | 'available' | 'downloading' | 'downloaded' | 'error';

export interface UpdateStatus {
  kind: UpdateStatusKind;
  version?: string;
  message?: string;
  percent?: number;
}

export interface RunOptions {
  whisper_model: 'tiny' | 'base' | 'small' | 'medium' | 'large' | 'large-v3-turbo';
  skip_isolation: boolean;
  skip_diarization: boolean;
  language: string;
  polish: 'off' | 'cli' | 'claude';
  output_dir?: string;
}

export interface Toast {
  id: string;
  kind: 'error' | 'warning' | 'info';
  title: string;
  body?: string;
}

