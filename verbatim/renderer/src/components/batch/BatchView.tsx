import { useEffect, useMemo, useRef, useState } from 'react';
import { Play, Square, Search, ScanLine } from 'lucide-react';
import { FileItem, FileProgress, PhaseName, RunOptions } from '../../types';
import { FileList } from './FileList';
import { BatchProgress } from './BatchProgress';
import { FolderPicker } from './FolderPicker';
import { RunSettingsPopover } from './RunSettingsPopover';
import { Button } from '../ui/Button';
import { verbatimClient } from '../../bridge/verbatimClient';

interface Props {
  onStart: () => void;
  onStop: () => void;
  running: boolean;
  settingsRevision: number;
  setRunning: (v: boolean) => void;
  pushToast: (t: { kind: 'error' | 'warning' | 'info'; title: string; body?: string }) => void;
}

export function BatchView({ onStart, onStop, running, settingsRevision, setRunning, pushToast }: Props) {
  const [inputDir, setInputDir] = useState('');
  const [outputDir, setOutputDir] = useState('');
  const [files, setFiles] = useState<FileItem[]>([]);
  const [scanned, setScanned] = useState(false);
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const [progress, setProgress] = useState<Record<string, FileProgress>>({});
  const [sortKey, setSortKey] = useState<'name' | 'duration' | 'size'>('name');
  const [batchStartedAt, setBatchStartedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [currentFile, setCurrentFile] = useState<string | undefined>();
  const [opts, setOpts] = useState<RunOptions>({
    whisper_model: 'large-v3-turbo',
    language: 'auto',
    skip_isolation: false,
    skip_diarization: false,
    polish: 'cli',
  });

  const elapsedTimer = useRef<number | null>(null);
  const inputDirDirtyRef = useRef(false);
  const outputDirDirtyRef = useRef(false);

  useEffect(() => {
    let alive = true;

    verbatimClient.getSettings().then((settings) => {
      if (!alive) {
        return;
      }
      if (!inputDirDirtyRef.current) {
        setInputDir(settings.defInput);
      }
      if (!outputDirDirtyRef.current) {
        setOutputDir(settings.defOutput);
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
        if (elapsedTimer.current) window.clearInterval(elapsedTimer.current);
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
            const cur = prev[ev.path];
            if (!cur) return prev;
            return {
              ...prev,
              [ev.path]: {
                ...cur,
                completedPhases: [...cur.completedPhases, ev.phase as PhaseName],
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
          setCurrentFile(undefined);
          setRunning(false);
          break;
        case 'cancel_accepted':
          setCurrentFile(undefined);
          setRunning(false);
          break;
        case 'error':
          if (ev.file) {
            setProgress((prev) => {
              const current = prev[ev.file];
              if (!current) {
                return prev;
              }
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
              if (!current) {
                return prev;
              }
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
  }, [pushToast, setRunning]);

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
    const processed = files.filter((f) => f.alreadyProcessed).length;
    const fresh = total - processed;
    return { total, fresh, processed };
  }, [files]);

  const completedCount = useMemo(
    () => Object.values(progress).filter((p) => p.state === 'success' || p.state === 'failed').length,
    [progress],
  );

  const toggle = (path: string) => {
    setSelection((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };
  const toggleAll = (v: boolean) => {
    if (v) setSelection(new Set(files.filter((f) => !f.alreadyProcessed).map((f) => f.path)));
    else setSelection(new Set());
  };

  const handleScan = async () => {
    const path = inputDir.trim();
    if (!path) {
      pushToast({ kind: 'warning', title: 'Missing input folder', body: 'Type or paste a folder path first.' });
      return;
    }

    pushToast({ kind: 'info', title: 'Scanning', body: path });
    try {
      await verbatimClient.send({
        type: 'scan_files',
        inputDir: path,
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

  const handleBrowse = (_label: string, _setter: (v: string) => void) => {
    pushToast({
      kind: 'info',
      title: 'Folder picker not wired yet',
      body: 'Type or paste the folder path for now.',
    });
  };

  const handleStart = async () => {
    const toProcess = sortedFiles.filter((f) => selection.has(f.path));
    if (toProcess.length === 0) {
      pushToast({ kind: 'warning', title: 'Nothing selected', body: 'Select at least one file to start.' });
      return;
    }
    setProgress({});
    try {
      await verbatimClient.send({
        type: 'process_batch',
        files: toProcess,
        options: { ...opts, output_dir: outputDir },
      });
      onStart();
    } catch (error) {
      pushToast({
        kind: 'error',
        title: 'Batch failed to start',
        body: error instanceof Error ? error.message : 'The daemon rejected the batch command.',
      });
    }
  };

  const handleCancel = async () => {
    try {
      await verbatimClient.send({ type: 'cancel_batch' });
      onStop();
    } catch (error) {
      pushToast({
        kind: 'error',
        title: 'Cancel failed',
        body: error instanceof Error ? error.message : 'The daemon rejected the cancel command.',
      });
    }
  };

  return (
    <div className="flex flex-col h-full gap-3 p-4 min-h-0">
      <div className="flex items-end gap-2">
        <FolderPicker
          label="Input folder"
          value={inputDir}
          onChange={(value) => {
            inputDirDirtyRef.current = true;
            setInputDir(value);
          }}
          onBrowse={() => handleBrowse('Input folder', setInputDir)}
          disabled={running}
        />
        <FolderPicker
          label="Output folder"
          value={outputDir}
          onChange={(value) => {
            outputDirDirtyRef.current = true;
            setOutputDir(value);
          }}
          onBrowse={() => handleBrowse('Output folder', setOutputDir)}
          disabled={running}
        />
        <Button
          variant="secondary"
          onClick={handleScan}
          disabled={running}
          leftIcon={<ScanLine size={13} />}
        >
          Scan
        </Button>
      </div>

      {scanned && (
        <div className="flex items-center gap-3 text-xs text-ink-400 -mt-1">
          <Search size={11} className="text-ink-500" />
          <span>
            <span className="text-ink-100 font-mono tabular-nums">{scanSummary.total}</span> files found Ã‚Â·{' '}
            <span className="text-accent font-mono tabular-nums">{scanSummary.fresh}</span> new Ã‚Â·{' '}
            <span className="font-mono tabular-nums">{scanSummary.processed}</span> already processed
          </span>
          <span className="ml-auto text-2xs text-ink-500">
            {selection.size} selected
          </span>
        </div>
      )}

      {running && batchStartedAt && (
        <BatchProgress
          total={selection.size}
          completed={completedCount}
          currentFile={currentFile?.split(/[\\/]/).pop()}
          elapsedSec={elapsed}
        />
      )}

      <FileList
        files={sortedFiles}
        progress={progress}
        selection={selection}
        onToggle={toggle}
        onToggleAll={toggleAll}
        running={running}
        sortKey={sortKey}
        onSort={setSortKey}
      />

      <div className="flex items-center gap-2 shrink-0">
        <div className="flex items-stretch">
          <Button
            variant="primary"
            size="md"
            onClick={handleStart}
            disabled={running || selection.size === 0}
            leftIcon={<Play size={13} fill="currentColor" />}
            className="rounded-r-none"
          >
            Start
          </Button>
          <RunSettingsPopover value={opts} onChange={setOpts} />
        </div>

        {running && (
          <Button variant="danger" onClick={handleCancel} leftIcon={<Square size={12} fill="currentColor" />}>
            Cancel
          </Button>
        )}

        <div className="ml-auto flex items-center gap-3 text-2xs text-ink-500 font-mono">
          <span>model: <span className="text-ink-300">{opts.whisper_model}</span></span>
          <span>Ã‚Â·</span>
          <span>lang: <span className="text-ink-300">{opts.language}</span></span>
          <span>Ã‚Â·</span>
          <span>polish: <span className="text-ink-300">{opts.polish}</span></span>
          {opts.skip_isolation && <span className="text-amber-400">Ã‚Â· no-isolation</span>}
          {opts.skip_diarization && <span className="text-amber-400">Ã‚Â· no-diarize</span>}
        </div>
      </div>
    </div>
  );
}



