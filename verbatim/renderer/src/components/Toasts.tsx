import { useEffect } from 'react';
import { X, AlertTriangle, AlertCircle, Info } from 'lucide-react';
import { Toast } from '../types';
import { cn } from '../lib/cn';

interface Props {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}

const META = {
  error: { icon: <AlertCircle size={14} />, className: 'border-red-500/40 text-red-100 bg-red-500/[0.08]', iconCls: 'text-red-400', duration: 8000 },
  warning: { icon: <AlertTriangle size={14} />, className: 'border-amber-500/40 text-amber-50 bg-amber-500/[0.08]', iconCls: 'text-amber-400', duration: 5000 },
  info: { icon: <Info size={14} />, className: 'border-ink-600 text-ink-100 bg-ink-850', iconCls: 'text-accent', duration: 4000 },
} as const;

function ToastItem({ t, onDismiss }: { t: Toast; onDismiss: (id: string) => void }) {
  const m = META[t.kind];
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(t.id), m.duration);
    return () => clearTimeout(timer);
  }, [t.id, m.duration, onDismiss]);

  return (
    <div
      className={cn(
        'relative min-w-[280px] max-w-[380px] rounded-lg border shadow-pop pl-3 pr-8 py-2.5 animate-fadeIn',
        m.className,
      )}
    >
      <div className="flex gap-2">
        <span className={cn('mt-0.5 shrink-0', m.iconCls)}>{m.icon}</span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-ink-50">{t.title}</div>
          {t.body && <div className="text-xs text-ink-300 mt-0.5 break-words">{t.body}</div>}
        </div>
      </div>
      <button
        onClick={() => onDismiss(t.id)}
        className="absolute top-2 right-2 p-0.5 rounded text-ink-400 hover:text-ink-50 hover:bg-white/[0.06]"
      >
        <X size={12} />
      </button>
    </div>
  );
}

export function Toasts({ toasts, onDismiss }: Props) {
  return (
    <div className="fixed bottom-12 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <ToastItem key={t.id} t={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
