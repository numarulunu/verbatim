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
        'h-10 w-full rounded-[4px] border border-transparent bg-transparent px-0 text-[12px] text-ink-50 placeholder:text-ink-500',
        'focus:outline-none transition-colors',
        'disabled:opacity-50',
        mono && 'font-mono text-xs',
        className,
      )}
      {...rest}
    />
  ),
);
Input.displayName = 'Input';
