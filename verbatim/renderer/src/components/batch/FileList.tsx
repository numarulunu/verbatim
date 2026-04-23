import { ArrowDownUp } from 'lucide-react';
import { FileItem, FileProgress } from '../../types';
import { FileRow } from './FileRow';

interface Props {
  files: FileItem[];
  progress: Record<string, FileProgress>;
  selection: Set<string>;
  onToggle: (path: string) => void;
  onToggleAll: (v: boolean) => void;
  running: boolean;
  sortKey: 'name' | 'duration' | 'size';
  onSort: (k: 'name' | 'duration' | 'size') => void;
}

const QUEUE_GRID = '28px minmax(0, 1fr) 92px 72px 120px';

export function FileList({
  files,
  progress,
  selection,
  onToggle,
  onToggleAll,
  running,
  sortKey,
  onSort,
}: Props) {
  const SortBtn = ({ k, label }: { k: 'name' | 'duration' | 'size'; label: string }) => (
    <button
      type='button'
      onClick={() => onSort(k)}
      className={`inline-flex items-center gap-1 text-left transition-colors ${
        sortKey === k ? 'text-ink-100' : 'text-ink-500 hover:text-ink-200'
      }`}
    >
      {label}
      <ArrowDownUp size={10} className={sortKey === k ? 'opacity-100' : 'opacity-40'} />
    </button>
  );

  const allSelected = files.length > 0 && files.filter((f) => !f.alreadyProcessed).every((f) => selection.has(f.path));

  return (
    <div className='shell-queue__table flex-1 min-h-0'>
      <div className='shell-queue__table-head' style={{ gridTemplateColumns: QUEUE_GRID }}>
        <input
          type='checkbox'
          checked={allSelected}
          onChange={(e) => onToggleAll(e.target.checked)}
          disabled={running || files.length === 0}
          className='shell-queue__check'
        />
        <SortBtn k='name' label='Filename' />
        <span>Class</span>
        <SortBtn k='size' label='Size' />
        <span>Status</span>
      </div>

      {files.length === 0 ? (
        <div className='shell-queue__empty-row'>
          <div className='shell-queue__empty-copy'>
            <span className='shell-kicker'>Queue</span>
            <span>Pick an input folder to load files.</span>
          </div>
        </div>
      ) : (
        <div className='shell-queue__rows'>
          {files.map((f) => (
            <FileRow
              key={f.path}
              file={f}
              progress={progress[f.path]}
              selected={selection.has(f.path)}
              onToggle={() => onToggle(f.path)}
              running={running}
            />
          ))}
        </div>
      )}
    </div>
  );
}
