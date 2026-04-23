import { Cpu, HardDrive, MemoryStick, Zap } from 'lucide-react';
import { ResourceStats } from '../types';
import { cn } from '../lib/cn';

interface Props {
  stats: ResourceStats;
  active?: boolean;
}

function Stat({
  icon,
  label,
  value,
  sub,
  intensity,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  intensity?: number; // 0..1 colors the value
}) {
  const hot = (intensity ?? 0) > 0.75;
  const warm = (intensity ?? 0) > 0.5;
  return (
    <div className="flex items-center gap-2 pr-4 border-r divider h-full">
      <span className="text-ink-500">{icon}</span>
      <div className="flex items-baseline gap-1.5">
        <span className="text-2xs text-ink-500 uppercase tracking-wider">{label}</span>
        <span
          className={cn(
            'text-xs font-mono tabular-nums transition-colors',
            hot ? 'text-accent' : warm ? 'text-ink-50' : 'text-ink-200',
          )}
        >
          {value}
        </span>
        {sub && <span className="text-2xs text-ink-500 font-mono">{sub}</span>}
      </div>
    </div>
  );
}

export function BottomBar({ stats, active }: Props) {
  return (
    <footer className="h-8 shrink-0 flex items-center gap-4 px-3 border-t divider surface-1">
      <Stat
        icon={<Cpu size={12} />}
        label="CPU"
        value={`${stats.cpu_pct.toFixed(0)}%`}
        intensity={stats.cpu_pct / 100}
      />
      <Stat
        icon={<Zap size={12} />}
        label="GPU"
        value={`${stats.gpu_pct.toFixed(0)}%`}
        sub={`${stats.gpu_mem_used_gb.toFixed(1)}/${stats.gpu_mem_total_gb.toFixed(0)}G`}
        intensity={stats.gpu_pct / 100}
      />
      <Stat
        icon={<MemoryStick size={12} />}
        label="RAM"
        value={`${stats.ram_used_gb.toFixed(1)}G`}
        sub={`/ ${stats.ram_total_gb.toFixed(0)}G`}
        intensity={stats.ram_used_gb / stats.ram_total_gb}
      />
      <Stat
        icon={<HardDrive size={12} />}
        label="Free"
        value={`${stats.disk_free_gb.toFixed(0)}G`}
      />

      <div className="ml-auto flex items-center gap-2 text-2xs text-ink-500">
        <span className={cn('w-1.5 h-1.5 rounded-full', active ? 'bg-accent animate-pulseSoft' : 'bg-ink-600')} />
        <span className="font-mono">{active ? 'live' : 'idle'}</span>
      </div>
    </footer>
  );
}
