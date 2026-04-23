import { PHASES, PHASE_LABELS, PhaseName } from '../../types';
import { cn } from '../../lib/cn';

interface Props {
  completed: PhaseName[];
  current?: PhaseName;
  compact?: boolean;
}

export function PhaseChiclets({ completed, current, compact }: Props) {
  return (
    <div className="flex items-center gap-[3px]">
      {PHASES.map((p, i) => {
        const isDone = completed.includes(p);
        const isCurrent = current === p;
        return (
          <div
            key={p}
            title={`${i + 1}. ${PHASE_LABELS[p]}`}
            className={cn(
              'rounded-sm transition-all duration-200 ease-out-soft',
              compact ? 'w-1.5 h-3' : 'w-2 h-4',
              isDone && 'bg-accent/70',
              isCurrent && 'bg-accent animate-pulseSoft shadow-[0_0_8px_rgba(124,92,255,0.7)]',
              !isDone && !isCurrent && 'bg-ink-700/70',
            )}
          />
        );
      })}
    </div>
  );
}
