import { cn } from '../../lib/cn';

export function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <label className="flex items-start justify-between gap-2.5 py-0.5 cursor-pointer group">
      <div className="min-w-0">
        <div className="text-[13px] text-ink-100 group-hover:text-ink-50">{label}</div>
        {description && <div className="text-[11px] text-ink-400 mt-0.5">{description}</div>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative shrink-0 w-[34px] h-[18px] rounded-full transition-colors duration-150 ease-out-soft mt-0.5',
          checked ? 'bg-accent' : 'bg-ink-600',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform duration-150 ease-out-soft',
            checked && 'translate-x-[16px]',
          )}
        />
      </button>
    </label>
  );
}
