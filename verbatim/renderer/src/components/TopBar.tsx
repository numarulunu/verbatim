import { Settings, Radio } from 'lucide-react';
import { DaemonStatus } from '../types';
import { cn } from '../lib/cn';

interface Props {
  tab: 'batch' | 'registry' | 'redo';
  onTab: (t: 'batch' | 'registry' | 'redo') => void;
  status: DaemonStatus;
  lastError?: string;
  onOpenSettings: () => void;
}

const STATUS_META: Record<DaemonStatus, { label: string; color: string; pulse?: boolean }> = {
  down: { label: 'Daemon down', color: 'bg-ink-400' },
  spawning: { label: 'Spawning', color: 'bg-amber-400', pulse: true },
  ready: { label: 'Ready', color: 'bg-emerald-400' },
  busy: { label: 'Processing', color: 'bg-accent', pulse: true },
  shutting_down: { label: 'Shutting down', color: 'bg-amber-400', pulse: true },
  crashed: { label: 'Crashed', color: 'bg-red-500' },
};

const TABS: { id: 'batch' | 'registry' | 'redo'; label: string; hint: string }[] = [
  { id: 'batch', label: 'Batch', hint: '⌘1' },
  { id: 'registry', label: 'Registry', hint: '⌘2' },
  { id: 'redo', label: 'Redo', hint: '⌘3' },
];

export function TopBar({ tab, onTab, status, lastError, onOpenSettings }: Props) {
  const meta = STATUS_META[status];

  return (
    <header className="h-12 shrink-0 flex items-center px-3 border-b divider surface-1 relative">
      {/* Brand */}
      <div className="flex items-center gap-2 pr-4 mr-2 border-r divider h-full">
        <div className="w-6 h-6 rounded bg-gradient-to-br from-accent to-[#4B2BD0] flex items-center justify-center shadow-[0_0_12px_rgba(124,92,255,0.35)]">
          <Radio size={13} className="text-white" />
        </div>
        <span className="text-sm font-semibold tracking-tight">Verbatim</span>
        <span className="text-2xs text-ink-500 font-mono mt-0.5">0.2.0</span>
      </div>

      {/* Tabs */}
      <nav className="flex items-center gap-0.5">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => onTab(t.id)}
            className={cn(
              'group relative h-8 px-3 rounded text-sm transition-colors duration-150 ease-out-soft flex items-center gap-2',
              tab === t.id
                ? 'text-ink-50 bg-white/[0.06]'
                : 'text-ink-300 hover:text-ink-50 hover:bg-white/[0.03]',
            )}
          >
            {t.label}
            <span
              className={cn(
                'text-2xs font-mono transition-opacity',
                tab === t.id ? 'text-ink-400 opacity-100' : 'opacity-0 group-hover:opacity-70 text-ink-500',
              )}
            >
              {t.hint}
            </span>
            {tab === t.id && (
              <span className="absolute -bottom-[9px] left-2 right-2 h-[2px] bg-accent rounded-full" />
            )}
          </button>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-3">
        {/* Status */}
        <div className="flex items-center gap-2 px-2.5 h-7 rounded bg-ink-850 border border-ink-700/60">
          <span className="relative flex w-2 h-2">
            <span className={cn('absolute inset-0 rounded-full', meta.color, meta.pulse && 'animate-ping opacity-60')} />
            <span className={cn('relative w-2 h-2 rounded-full', meta.color)} />
          </span>
          <span className="text-xs text-ink-100">{meta.label}</span>
          {lastError && status === 'crashed' && (
            <span className="text-2xs text-red-400 font-mono truncate max-w-[180px]">{lastError}</span>
          )}
        </div>

        <button
          onClick={onOpenSettings}
          className="p-1.5 rounded text-ink-400 hover:text-ink-50 hover:bg-white/[0.05] transition-colors btn-focus"
          title="Settings (⌘,)"
        >
          <Settings size={16} />
        </button>
      </div>
    </header>
  );
}
