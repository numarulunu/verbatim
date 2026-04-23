import { FileAudio } from 'lucide-react';
import { FileItem, FileProgress, PHASE_LABELS } from '../../types';
import { fmtDuration, fmtSize, truncateMiddle } from '../../lib/format';
import { cn } from '../../lib/cn';

interface Props {
  file: FileItem;
  progress?: FileProgress;
  selected: boolean;
  onToggle: () => void;
  running: boolean;
}

const QUEUE_GRID = '28px minmax(0, 1fr) 92px 72px 120px';

function classLabel(progress?: FileProgress, alreadyProcessed?: boolean) {
  if (progress?.state === 'failed') return 'Error';
  if (progress?.state === 'running') return 'Active';
  if (alreadyProcessed) return 'Done';
  return 'Audio';
}

function statusLabel(progress?: FileProgress, alreadyProcessed?: boolean) {
  if (!progress || progress.state === 'idle') {
    return alreadyProcessed ? 'Processed' : 'Queued';
  }

  switch (progress.state) {
    case 'queued':
      return 'Queued';
    case 'running':
      return progress.currentPhase ? PHASE_LABELS[progress.currentPhase] ?? 'Running' : 'Running';
    case 'success':
      return 'Processed';
    case 'failed':
      return 'Failed';
    case 'skipped':
      return 'Skipped';
  }
}

function statusTone(progress?: FileProgress, alreadyProcessed?: boolean) {
  if (progress?.state === 'failed') return 'shell-queue__state shell-queue__state--failed';
  if (progress?.state === 'running') return 'shell-queue__state shell-queue__state--running';
  if (progress?.state === 'success' || alreadyProcessed) return 'shell-queue__state shell-queue__state--done';
  return 'shell-queue__state';
}

export function FileRow({ file, progress, selected, onToggle, running }: Props) {
  const isActive = progress?.state === 'running';
  const isDone = progress?.state === 'success' || file.alreadyProcessed;
  const isFail = progress?.state === 'failed';
  const metaLine = isActive
    ? `${fmtDuration(file.duration)} • ${Math.round((progress?.phaseProgress ?? 0) * 100)}%`
    : truncateMiddle(file.path, 72);

  return (
    <div
      className={cn(
        'shell-queue__row',
        isActive && 'shell-queue__row--running',
        isDone && !isActive && 'shell-queue__row--done',
        isFail && 'shell-queue__row--failed',
      )}
      style={{ gridTemplateColumns: QUEUE_GRID }}
    >
      <input
        type='checkbox'
        checked={selected}
        onChange={onToggle}
        disabled={running || file.alreadyProcessed}
        className='shell-queue__check'
      />

      <div className='shell-queue__file'>
        <div className='shell-queue__file-name' title={file.path}>
          <FileAudio size={13} className={cn('shrink-0', isActive ? 'text-accent' : 'text-ink-500')} />
          <span className={cn(file.alreadyProcessed && !progress && 'text-ink-400')}>{file.name}</span>
        </div>
        <div className='shell-queue__file-meta'>{metaLine}</div>
      </div>

      <div className='shell-queue__class'>{classLabel(progress, file.alreadyProcessed)}</div>
      <div className='shell-queue__size'>{fmtSize(file.size)}</div>
      <div className={statusTone(progress, file.alreadyProcessed)}>{statusLabel(progress, file.alreadyProcessed)}</div>
    </div>
  );
}
