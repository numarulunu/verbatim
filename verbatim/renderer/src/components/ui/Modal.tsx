import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { cn } from '../../lib/cn';

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: string;
}

export function Modal({ open, onClose, title, description, children, footer, width = 'max-w-xl' }: Props) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center animate-fadeIn">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <div
        className={cn(
          'relative surface-2 hairline rounded-lg shadow-pop w-full mx-4',
          width,
          'max-h-[80vh] flex flex-col',
        )}
      >
        <div className="flex items-start justify-between px-5 pt-4 pb-3 border-b divider">
          <div>
            <h2 className="text-md font-semibold text-ink-50">{title}</h2>
            {description && <p className="text-xs text-ink-400 mt-0.5">{description}</p>}
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded text-ink-400 hover:text-ink-50 hover:bg-white/[0.05] transition-colors"
          >
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="px-5 py-3 border-t divider flex items-center justify-end gap-2 bg-ink-900/40 rounded-b-lg">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
