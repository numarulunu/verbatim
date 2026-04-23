export interface RendererCommand {
  type?: string;
  cmd?: string;
  id?: string | null;
  [key: string]: unknown;
}

export interface DaemonCommand {
  cmd: string;
  [key: string]: unknown;
}

function readString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function normalizeFiles(files: unknown): string[] {
  if (!Array.isArray(files)) {
    return [];
  }

  return files.map((item) => {
    if (typeof item === 'string') {
      return item;
    }

    if (item && typeof item === 'object') {
      const path = readString((item as { path?: unknown }).path);
      if (path) {
        return path;
      }
    }

    throw new TypeError('encodeRendererCommand: process_batch files must be strings or { path } objects');
  });
}

export function encodeRendererCommand(command: RendererCommand): DaemonCommand {
  if (!command || typeof command !== 'object') {
    throw new TypeError('encodeRendererCommand: command must be an object');
  }

  const cmd = readString(command.cmd) ?? readString(command.type);
  if (!cmd) {
    throw new TypeError('encodeRendererCommand: command needs `cmd` or `type`');
  }

  const payload: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(command)) {
    if (key !== 'type') {
      payload[key] = value;
    }
  }

  payload.cmd = cmd;

  if (cmd === 'process_batch') {
    payload.files = normalizeFiles(command.files);
  }

  if (cmd === 'scan_files' && typeof command.inputDir === 'string' && typeof payload.input_dir !== 'string') {
    payload.input_dir = command.inputDir;
  }

  if (cmd === 'scan_files') {
    delete payload.inputDir;
  }

  if (cmd === 'scan_files' && typeof payload.probe_duration !== 'boolean') {
    payload.probe_duration = true;
  }

  return { ...payload, cmd };
}
