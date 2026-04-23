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

  if (files.length === 0) {
    return (
      <div className='shell-queue__table flex-1 min-h-0'>
        <div className='shell-queue__table-head' style={{ gridTemplateColumns: QUEUE_GRID }}>
          <input
            type='checkbox'
            checked={false}
            disabled
            className='w-3.5 h-3.5 rounded accent-[#7C5CFF] bg-ink-800 disabled:opacity-40'
          />
          <span>File</span>
          <span>Duration</span>
          <span>Size</span>
          <span>State</span>
        </div>
        <div className='shell-queue__empty-row'>
          <div className='shell-queue__empty-copy'>
            <span className='shell-kicker'>Queue empty</span>
            <span>Pick an input folder to load files into this queue.</span>
          </div>
        </div>
      </div>
    );
  }

  const allSelected = files.length > 0 && files.filter((f) => !f.alreadyProcessed).every((f) => selection.has(f.path));

  return (
    <div className='shell-queue__table flex-1 min-h-0'>
      <div className='shell-queue__table-head' style={{ gridTemplateColumns: QUEUE_GRID }}>
        <input
          type='checkbox'
          checked={allSelected}
          onChange={(e) => onToggleAll(e.target.checked)}
          disabled={running}
          className='w-3.5 h-3.5 rounded accent-[#7C5CFF] bg-ink-800 disabled:opacity-40'
        />
        <SortBtn k='name' label='File' />
        <SortBtn k='duration' label='Duration' />
        <SortBtn k='size' label='Size' />
        <span>State</span>
      </div>

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
    </div>
  );
}
