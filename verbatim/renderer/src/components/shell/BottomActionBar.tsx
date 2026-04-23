import { ArrowRight, Square } from 'lucide-react';
import type { DaemonStatus, ResourceStats } from '../../types';

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
  elapsed,
  stats,
  onStart,
  onCancel,
  onOpenOutput,
}: {
  running: boolean;
  status: DaemonStatus;
  selectedCount: number;
  completedCount: number;
  elapsed: number;
  stats: ResourceStats;
  onStart: () => Promise<void>;
  onCancel: () => Promise<void>;
  onOpenOutput: () => Promise<void>;
}) {
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
