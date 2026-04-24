import { useEffect, useState } from 'react';
import { ArrowRight, Square } from 'lucide-react';
import type { DaemonStatus } from '../../types';

// elapsed used to live on App state and ticked twice per second, forcing
// the entire App tree (QueuePane, SettingsRail, the 16-file-table FileList)
// to rerun on every tick. The interval now lives here so only the footer
// re-renders (SMAC 2026-04-23 Finding 15).
//
// The 1 Hz `resource_stats` event stream was previously wired into App-
// level state but never rendered — the BottomBar that consumed it was dead
// code (deleted with this commit). If/when we bring back a resource
// readout, the subscription belongs here for the same reason.

function useElapsedSeconds(running: boolean, batchStartedAt: number | null): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!running || !batchStartedAt) {
      setSeconds(0);
      return;
    }
    setSeconds((Date.now() - batchStartedAt) / 1000);
    const id = window.setInterval(() => {
      setSeconds((Date.now() - batchStartedAt) / 1000);
    }, 500);
    return () => window.clearInterval(id);
  }, [running, batchStartedAt]);
  return seconds;
}

function statusMessage(status: DaemonStatus, running: boolean, selectedCount: number) {
  if (running) return `Processing ${selectedCount} file${selectedCount === 1 ? '' : 's'}.`;
  if (status === 'ready') return selectedCount > 0 ? `${selectedCount} files ready.` : 'Choose folders and scan to begin.';
  if (status === 'spawning') return 'Starting the engine.';
  if (status === 'crashed') return 'Engine crashed. Open settings and restart after checking tokens and paths.';
  return 'Engine offline.';
}

function detailLine(selectedCount: number) {
  return selectedCount > 0 ? `${selectedCount} selected | ready to start.` : 'Queue idle | choose folders to begin.';
}

export function BottomActionBar({
  running,
  status,
  selectedCount,
  completedCount,
  batchStartedAt,
  onStart,
  onCancel,
  onOpenOutput,
}: {
  running: boolean;
  status: DaemonStatus;
  selectedCount: number;
  completedCount: number;
  batchStartedAt: number | null;
  onStart: () => Promise<void>;
  onCancel: () => Promise<void>;
  onOpenOutput: () => Promise<void>;
}) {
  const elapsed = useElapsedSeconds(running, batchStartedAt);

  const disabled = !running && selectedCount === 0;
  const progress = running && selectedCount > 0 ? Math.round((completedCount / selectedCount) * 100) : 0;

  return (
    <footer className='shell-action'>
      {running ? <div className='shell-action__progress' style={{ width: `${progress}%` }} /> : null}

      <button
        type='button'
        onClick={() => { void (running ? onCancel() : onStart()); }}
        disabled={disabled}
        className={running ? 'shell-action__button shell-action__button--stop' : 'shell-action__button shell-action__button--start'}
      >
        {running ? <Square size={14} strokeWidth={1.6} /> : null}
        <span>{running ? 'Stop' : 'Start'}</span>
        {!running ? <ArrowRight size={14} strokeWidth={1.6} /> : null}
      </button>

      <div className='shell-action__body'>
        <div className='shell-action__copy'>
          <div className='shell-action__headline'>{statusMessage(status, running, selectedCount)}</div>
          <div className='shell-action__detail'>
            {running ? `${completedCount}/${selectedCount} complete | ${Math.round(elapsed)}s elapsed` : detailLine(selectedCount)}
          </div>
        </div>

        <button type='button' className='shell-action__link' onClick={() => { void onOpenOutput(); }}>
          Open output folder
        </button>
      </div>
    </footer>
  );
}
