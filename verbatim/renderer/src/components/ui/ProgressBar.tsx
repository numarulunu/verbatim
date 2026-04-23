import { cn } from '../../lib/cn';

export function ProgressBar({
  value,
  indeterminate,
  pulse,
  height = 4,
  className,
}: {
  value?: number; // 0..1
  indeterminate?: boolean;
  pulse?: boolean;
  height?: number;
  className?: string;
}) {
  return (
    <div
      className={cn('w-full rounded-full bg-ink-700/60 overflow-hidden relative', className)}
      style={{ height }}
    >
      {indeterminate ? (
        <div className="absolute inset-0 shimmer animate-shimmer rounded-full" />
      ) : (
        <div
          className={cn(
            'h-full rounded-full bg-accent transition-[width] duration-200 ease-out-soft',
            pulse && 'animate-pulseSoft',
          )}
          style={{ width: `${Math.max(0, Math.min(1, value ?? 0)) * 100}%` }}
        />
      )}
    </div>
  );
}
