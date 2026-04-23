import React from 'react';
import { cn } from '../../lib/cn';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

interface Props extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const base =
  'inline-flex items-center justify-center gap-1.5 rounded-[6px] border text-sm font-medium transition-all duration-150 ease-out-soft btn-focus disabled:opacity-40 disabled:cursor-not-allowed select-none';

const sizes: Record<Size, string> = {
  sm: 'h-[30px] px-3 text-xs',
  md: 'h-10 px-3.5 text-[13px]',
};

const variants: Record<Variant, string> = {
  primary:
    'bg-accent text-white border border-transparent hover:bg-accent-hover active:translate-y-[1px]',
  secondary:
    'bg-white/[0.02] text-ink-50 hover:bg-white/[0.05] border border-white/10 hover:border-white/15',
  ghost:
    'bg-transparent text-ink-200 hover:bg-white/[0.04] hover:text-ink-50 border border-transparent',
  danger:
    'bg-red-500/10 text-red-400 hover:bg-red-500/15 hover:text-white border border-red-500/20 hover:border-red-500/30',
};

export const Button = React.forwardRef<HTMLButtonElement, Props>(
  ({ className, variant = 'secondary', size = 'md', leftIcon, rightIcon, children, ...rest }, ref) => (
    <button ref={ref} className={cn(base, sizes[size], variants[variant], className)} {...rest}>
      {leftIcon && <span className="shrink-0 -ml-0.5 opacity-90">{leftIcon}</span>}
      {children}
      {rightIcon && <span className="shrink-0 -mr-0.5 opacity-90">{rightIcon}</span>}
    </button>
  ),
);
Button.displayName = 'Button';
