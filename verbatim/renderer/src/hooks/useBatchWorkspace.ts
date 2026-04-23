import { useEffect, useMemo, useRef, useState } from 'react';
import { verbatimClient } from '../bridge/verbatimClient';
import { type FileItem, type FileProgress, type PhaseName, type RunOptions } from '../types';

export interface BatchWorkspaceController {
  inputDir: string;
  outputDir: string;
  files: FileItem[];
  sortedFiles: FileItem[];
  selection: Set<string>;
  progress: Record<string, FileProgress>;
  running: boolean;
  setRunning: (value: boolean) => void;
  scanned: boolean;
  sortKey: 'name' | 'duration' | 'size';
  scanSummary: { total: number; fresh: number; processed: number };
  completedCount: number;
  currentFile?: string;
  elapsed: number;
  opts: RunOptions;
  setSortKey: (value: 'name' | 'duration' | 'size') => void;
  setOpts: (value: RunOptions) => void;
  setInputDir: (value: string) => void;
  setOutputDir: (value: string) => void;
  toggle: (path: string) => void;
  toggleAll: (checked: boolean) => void;
  browseInput: () => Promise<void>;
  browseOutput: () => Promise<void>;
  scan: () => Promise<void>;
  refresh: () => Promise<void>;
  openOutput: () => Promise<void>;
  start: () => Promise<void>;
  cancel: () => Promise<void>;
}

const DEFAULT_OPTS: RunOptions = {
  whisper_model: 'large-v3-turbo',
  language: 'auto',
  skip_isolation: false,
  skip_diarization: false,
  polish: 'cli',
};

export function useBatchWorkspace({
  settingsRevision,
  pushToast,
}: {
  settingsRevision: number;
  pushToast: (toast: { kind: 'error' | 'warning' | 'info'; title: string; body?: string }) => void;
}): BatchWorkspaceController {
  const [inputDir, setInputDirState] = useState('');
  const [outputDir, setOutputDirState] = useState('');
  const [files, setFiles] = useState<FileItem[]>([]);
  const [scanned, setScanned] = useState(false);
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const [progress, setProgress] = useState<Record<string, FileProgress>>({});
  const [sortKey, setSortKey] = useState<'name' | 'duration' | 'size'>('name');
  const [batchStartedAt, setBatchStartedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [currentFile, setCurrentFile] = useState<string | undefined>();
  const [running, setRunning] = useState(false);
  const [opts, setOpts] = useState<RunOptions>(DEFAULT_OPTS);

  const elapsedTimer = useRef<number | null>(null);
  const inputDirDirtyRef = useRef(false);
  const outputDirDirtyRef = useRef(false);

  useEffect(() => {
    let alive = true;

    verbatimClient.getSettings().then((settings) => {
      if (!alive) return;

      if (!inputDirDirtyRef.current) {
        setInputDirState(settings.defInput);
      }
      if (!outputDirDirtyRef.current) {
        setOutputDirState(settings.defOutput);
      }
      setOpts((prev) => ({
        ...prev,
        whisper_model: settings.model as RunOptions['whisper_model'],
        language: settings.lang,
        polish: settings.polish as RunOptions['polish'],
      }));
    }).catch(() => {});

    return () => {
      alive = false;
    };
  }, [settingsRevision]);

  useEffect(() => {
    if (running && batchStartedAt) {
      elapsedTimer.current = window.setInterval(() => {
        setElapsed((Date.now() - batchStartedAt) / 1000);
      }, 500);

      return () => {
        if (elapsedTimer.current) {
          window.clearInterval(elapsedTimer.current);
        }
      };
    }
  }, [running, batchStartedAt]);

  useEffect(() => {
    if (!running) {
      setBatchStartedAt(null);
      setElapsed(0);
      setCurrentFile(undefined);
    }
  }, [running]);

  useEffect(() => {
    const off = verbatimClient.onEvent((ev: any) => {
      switch (ev.type) {
        case 'files_scanned':
          setFiles(ev.files);
          setScanned(true);
          setSelection(new Set(ev.files.filter((file: FileItem) => !file.alreadyProcessed).map((file: FileItem) => file.path)));
          setProgress({});
          break;
        case 'batch_started':
          setBatchStartedAt(Date.now());
          setElapsed(0);
          setRunning(true);
          break;
        case 'file_started':
          setCurrentFile(ev.path);
          setProgress((prev) => ({
            ...prev,
            [ev.path]: {
              state: 'running',
              completedPhases: [],
              currentPhase: undefined,
              currentPhaseIndex: 0,
              phaseProgress: 0,
              startedAt: Date.now(),
            },
          }));
          break;
        case 'phase_started':
          setProgress((prev) => ({
            ...prev,
            [ev.path]: {
              ...(prev[ev.path] || { state: 'running', completedPhases: [], currentPhaseIndex: 0, phaseProgress: 0 }),
              currentPhase: ev.phase as PhaseName,
              currentPhaseIndex: ev.phaseIndex,
              phaseProgress: 0,
              state: 'running',
            },
          }));
          break;
        case 'phase_progress':
          setProgress((prev) => ({
            ...prev,
            [ev.path]: {
              ...(prev[ev.path] || { state: 'running', completedPhases: [], currentPhaseIndex: 0, phaseProgress: 0 }),
              phaseProgress: ev.phase_progress,
            },
          }));
          break;
        case 'phase_complete':
          setProgress((prev) => {
            const current = prev[ev.path];
            if (!current) return prev;
            return {
              ...prev,
              [ev.path]: {
                ...current,
                completedPhases: [...current.completedPhases, ev.phase as PhaseName],
                phaseProgress: 1,
              },
            };
          });
          break;
        case 'file_complete':
          setProgress((prev) => ({
            ...prev,
            [ev.path]: {
              ...(prev[ev.path] || { state: 'success', completedPhases: [], currentPhaseIndex: 9, phaseProgress: 1 }),
              state: ev.state || 'success',
              currentPhase: undefined,
              phaseProgress: 1,
              endedAt: Date.now(),
            },
          }));
          break;
        case 'batch_complete':
        case 'cancel_accepted':
          setCurrentFile(undefined);
          setRunning(false);
          break;
        case 'error':
          if (ev.file) {
            setProgress((prev) => {
              const current = prev[ev.file];
              if (!current) return prev;
              return {
                ...prev,
                [ev.file]: {
                  ...current,
                  state: 'failed',
                  endedAt: Date.now(),
                  errorMessage: ev.body || ev.title,
                },
              };
            });
          }
          break;
        case 'warning':
          if (ev.file) {
            setProgress((prev) => {
              const current = prev[ev.file];
              if (!current) return prev;
              return {
                ...prev,
                [ev.file]: {
                  ...current,
                  errorMessage: ev.body || ev.title,
                },
              };
            });
          }
          break;
      }
    });

    return () => off();
  }, []);

  const sortedFiles = useMemo(() => {
    const copy = [...files];
    copy.sort((a, b) => {
      if (sortKey === 'name') return a.name.localeCompare(b.name);
      if (sortKey === 'duration') return b.duration - a.duration;
      return b.size - a.size;
    });
    return copy;
  }, [files, sortKey]);

  const scanSummary = useMemo(() => {
    const total = files.length;
    const processed = files.filter((file) => file.alreadyProcessed).length;
    const fresh = total - processed;
    return { total, fresh, processed };
  }, [files]);

  const completedCount = useMemo(
    () => Object.values(progress).filter((item) => item.state === 'success' || item.state === 'failed').length,
    [progress],
  );

  const setInputDir = (value: string) => {
    inputDirDirtyRef.current = true;
    setInputDirState(value);
  };

  const setOutputDir = (value: string) => {
    outputDirDirtyRef.current = true;
    setOutputDirState(value);
  };

  const toggle = (path: string) => {
    setSelection((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const toggleAll = (checked: boolean) => {
    if (checked) {
      setSelection(new Set(files.filter((file) => !file.alreadyProcessed).map((file) => file.path)));
      return;
    }
    setSelection(new Set());
  };

  const browseInput = async () => {
    const picked = await verbatimClient.pickFolder(inputDir.trim() || undefined);
    if (picked) {
      setInputDir(picked);
    }
  };

  const browseOutput = async () => {
    const picked = await verbatimClient.pickFolder(outputDir.trim() || undefined);
    if (picked) {
      setOutputDir(picked);
    }
  };

  const scan = async () => {
    const targetPath = inputDir.trim();
    if (!targetPath) {
      pushToast({ kind: 'warning', title: 'Missing input folder', body: 'Choose an input folder first.' });
      return;
    }

    try {
      await verbatimClient.send({
        type: 'scan_files',
        inputDir: targetPath,
        probe_duration: true,
      });
    } catch (error) {
      pushToast({
        kind: 'error',
        title: 'Scan failed',
        body: error instanceof Error ? error.message : 'The daemon rejected the scan command.',
      });
    }
  };

  const refresh = async () => {
    await scan();
  };

  const openOutput = async () => {
    const targetPath = outputDir.trim();
    if (!targetPath) {
      pushToast({ kind: 'warning', title: 'Missing output folder', body: 'Choose an output folder first.' });
      return;
    }

    try {
      const result = await verbatimClient.openPath(targetPath);
      if (!result.ok && result.error) {
        throw new Error(result.error);
      }
    } catch (error) {
      pushToast({
        kind: 'error',
        title: 'Open folder failed',
        body: error instanceof Error ? error.message : 'Could not open the output folder.',
      });
    }
  };

  const start = async () => {
    const toProcess = sortedFiles.filter((file) => selection.has(file.path));
    if (toProcess.length === 0) {
      pushToast({ kind: 'warning', title: 'Nothing selected', body: 'Select at least one file to start.' });
      return;
    }

    setProgress({});

    try {
      await verbatimClient.send({
        type: 'process_batch',
        files: toProcess,
        options: { ...opts, output_dir: outputDir.trim() },
      });
      setRunning(true);
    } catch (error) {
      pushToast({
        kind: 'error',
        title: 'Batch failed to start',
        body: error instanceof Error ? error.message : 'The daemon rejected the batch command.',
      });
    }
  };

  const cancel = async () => {
    try {
      await verbatimClient.send({ type: 'cancel_batch' });
      setRunning(false);
    } catch (error) {
      pushToast({
        kind: 'error',
        title: 'Cancel failed',
        body: error instanceof Error ? error.message : 'The daemon rejected the cancel command.',
      });
    }
  };

  return {
    inputDir,
    outputDir,
    files,
    sortedFiles,
    selection,
    progress,
    running,
    setRunning,
    scanned,
    sortKey,
    scanSummary,
    completedCount,
    currentFile,
    elapsed,
    opts,
    setSortKey,
    setOpts,
    setInputDir,
    setOutputDir,
    toggle,
    toggleAll,
    browseInput,
    browseOutput,
    scan,
    refresh,
    openOutput,
    start,
    cancel,
  };
}
