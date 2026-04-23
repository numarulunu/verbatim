import React from 'react';
import { cn } from '../../lib/cn';

interface Props extends React.InputHTMLAttributes<HTMLInputElement> {
  mono?: boolean;
}

export const Input = React.forwardRef<HTMLInputElement, Props>(
  ({ className, mono, ...rest }, ref) => (
    <input
      ref={ref}
      className={cn(
        'h-10 w-full rounded-[6px] border border-white/[0.08] bg-transparent px-3 text-[13px] text-ink-50 placeholder:text-ink-400',
        'hover:border-white/15 focus:border-accent focus:ring-1 focus:ring-accent-ring focus:outline-none transition-colors',
        'disabled:opacity-50',
        mono && 'font-mono text-xs',
        className,
      )}
      {...rest}
    />
  ),
);
Input.displayName = 'Input';
