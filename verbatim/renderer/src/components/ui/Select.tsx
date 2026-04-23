import React from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '../../lib/cn';

interface Option {
  value: string;
  label: string;
  description?: string;
}

interface Props {
  value: string;
  onChange: (v: string) => void;
  options: Option[];
  className?: string;
}

export function Select({ value, onChange, options, className }: Props) {
  return (
    <div className={cn('relative', className)}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          'h-10 w-full appearance-none rounded-[6px] bg-white/[0.02] border border-white/10 pl-3 pr-8 text-[13px] text-ink-50',
          'hover:border-white/15 focus:border-accent focus:ring-1 focus:ring-accent-ring focus:outline-none transition-colors',
        )}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value} className="bg-ink-850">
            {o.label}
            {o.description ? ` â€” ${o.description}` : ''}
          </option>
        ))}
      </select>
      <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-400" />
    </div>
  );
}
