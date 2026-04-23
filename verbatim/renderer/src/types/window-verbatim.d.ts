import type { RendererSettings, StatusEnvelope } from '../bridge/normalize';
import type { UpdateStatus } from '../types';

export interface VerbatimPreloadApi {
  minimizeWindow(): Promise<{ maximized: boolean }>;
  toggleMaximizeWindow(): Promise<{ maximized: boolean }>;
  closeWindow(): Promise<{ maximized: boolean }>;
  send(command: Record<string, unknown>): Promise<{ ok: true }>;
  onEvent(cb: (event: unknown) => void): () => void;
  onStatus(cb: (status: StatusEnvelope) => void): () => void;
  status(): Promise<StatusEnvelope>;
  restart(): Promise<{ ok: true }>;
  pickFolder(defaultPath?: string): Promise<string | null>;
  openPath(targetPath: string): Promise<{ ok: boolean; error: string | null }>;
  getSettings(): Promise<Partial<RendererSettings> | Record<string, unknown>>;
  saveSettings(settings: Record<string, unknown>): Promise<{ ok: true }>;
  updateStatus(): Promise<UpdateStatus | null>;
  onUpdateStatus(cb: (event: unknown) => void): () => void;
}

declare global {
  interface Window {
    verbatim: VerbatimPreloadApi;
  }
}

export {};
