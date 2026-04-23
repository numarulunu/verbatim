import React from 'react';
import { cn } from '../../lib/cn';

type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'muted';

const tones: Record<Tone, string> = {
  neutral: 'bg-ink-700/60 text-ink-100 border-ink-600/60',
  accent: 'bg-accent-soft text-accent border-accent/30',
  success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  warning: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  danger: 'bg-red-500/10 text-red-400 border-red-500/30',
  muted: 'bg-ink-800 text-ink-400 border-ink-700/60',
};

export function Pill({
  tone = 'neutral',
  children,
  className,
  icon,
}: {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
  icon?: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded border px-1.5 h-5 text-2xs font-medium tracking-wide',
        tones[tone],
        className,
      )}
    >
      {icon && <span className="opacity-80">{icon}</span>}
      {children}
    </span>
  );
}
