import { CheckCircle2, XCircle, Loader2, FileAudio, Circle } from 'lucide-react';
import { FileItem, FileProgress, PHASE_LABELS, PHASES } from '../../types';
import { fmtDuration, fmtSize, truncateMiddle } from '../../lib/format';
import { Pill } from '../ui/Pill';
import { ProgressBar } from '../ui/ProgressBar';
import { cn } from '../../lib/cn';

interface Props {
  file: FileItem;
  progress?: FileProgress;
  selected: boolean;
  onToggle: () => void;
  running: boolean;
}

function statusMeta(progress?: FileProgress, alreadyProcessed?: boolean) {
  if (!progress || progress.state === 'idle') {
    return alreadyProcessed ? 'processed' : 'queued';
  }
  switch (progress.state) {
    case 'queued':
      return 'queued';
    case 'running':
      return `running ${progress.currentPhaseIndex + 1}/${PHASES.length}`;
    case 'success':
      return 'processed';
    case 'failed':
      return 'failed';
    case 'skipped':
      return 'skipped';
  }
}

function statusPill(progress?: FileProgress, alreadyProcessed?: boolean) {
  if (!progress || progress.state === 'idle') {
    return alreadyProcessed ? <Pill tone='muted'>processed</Pill> : <Pill tone='neutral'>queued</Pill>;
  }

  switch (progress.state) {
    case 'queued':
      return <Pill tone='neutral'>queued</Pill>;
    case 'running':
      return (
        <Pill tone='accent' icon={<Loader2 size={10} className='animate-spin' />}>
          running
        </Pill>
      );
    case 'success':
      return (
        <Pill tone='success' icon={<CheckCircle2 size={10} />}>
          processed
        </Pill>
      );
    case 'failed':
      return (
        <Pill tone='danger' icon={<XCircle size={10} />}>
          failed
        </Pill>
      );
    case 'skipped':
      return <Pill tone='muted'>skipped</Pill>;
  }
}

export function FileRow({ file, progress, selected, onToggle, running }: Props) {
  const isActive = progress?.state === 'running';
  const isDone = progress?.state === 'success' || file.alreadyProcessed;
  const isFail = progress?.state === 'failed';
  const statusLine = statusMeta(progress, file.alreadyProcessed);
  const phaseLabel = isActive && progress?.currentPhase ? PHASE_LABELS[progress.currentPhase] ?? 'Running' : null;

  return (
    <div
      className={cn(
        'shell-queue__row group grid items-center',
        'hover:bg-white/[0.025] transition-colors',
        isActive && 'bg-accent/[0.05]',
        isDone && !isActive && 'bg-emerald-500/[0.03]',
        isFail && 'bg-red-500/[0.05]',
      )}
      style={{ gridTemplateColumns: '28px minmax(0, 1fr) 92px 72px 120px' }}
    >
      <input
        type='checkbox'
        checked={selected}
        onChange={onToggle}
        disabled={running || file.alreadyProcessed}
        className='w-3.5 h-3.5 rounded accent-[#7C5CFF] bg-ink-800 disabled:opacity-40'
      />

      <div className='min-w-0 flex flex-col justify-center gap-0.5 pr-1'>
        <div className='min-w-0 flex items-center gap-2'>
          <FileAudio size={13} className={cn('shrink-0', isActive ? 'text-accent' : 'text-ink-500')} />
          <div
            className={cn(
              'min-w-0 font-mono text-xs truncate leading-tight',
              isActive ? 'text-ink-50' : 'text-ink-100',
              file.alreadyProcessed && !progress && 'text-ink-400',
            )}
            title={file.path}
          >
            {file.name}
          </div>
        </div>
        {isActive ? (
          <div className='flex items-center gap-2 min-w-0'>
            <div className='min-w-0 flex-1'>
              <ProgressBar value={progress!.phaseProgress} height={2} pulse />
            </div>
            <span className='text-2xs text-ink-500 font-mono tabular-nums whitespace-nowrap'>
              {phaseLabel} ? {Math.round(progress!.phaseProgress * 100)}%
            </span>
          </div>
        ) : (
          <div className='text-2xs text-ink-500 font-mono truncate opacity-0 group-hover:opacity-100 transition-opacity'>
            {truncateMiddle(file.path, 80)}
          </div>
        )}
      </div>

      <span className='text-xs text-ink-400 font-mono tabular-nums'>{fmtDuration(file.duration)}</span>
      <span className='text-xs text-ink-400 font-mono tabular-nums'>{fmtSize(file.size)}</span>

      <div className='flex items-center justify-between gap-2 min-w-0'>
        <span className='text-2xs text-ink-500 font-mono uppercase tracking-[0.14em] truncate'>{statusLine}</span>
        {statusPill(progress, file.alreadyProcessed)}
      </div>
    </div>
  );
}
