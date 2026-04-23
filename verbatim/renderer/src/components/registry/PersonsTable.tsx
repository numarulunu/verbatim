import { Person } from '../../types';
import { Pill } from '../ui/Pill';
import { cn } from '../../lib/cn';

interface Props {
  persons: Person[];
  selectedId?: string;
  onSelect: (id: string) => void;
}

function RoleBadge({ role }: { role: Person['role'] }) {
  if (role === 'teacher') return <Pill tone="accent">teacher</Pill>;
  if (role === 'student') return <Pill tone="success">student</Pill>;
  return <Pill tone="muted">unknown</Pill>;
}

export function PersonsTable({ persons, selectedId, onSelect }: Props) {
  return (
    <div className="surface-2 hairline rounded-lg flex flex-col min-h-0 overflow-hidden">
      <div className="grid grid-cols-[140px_1fr_90px_80px_80px_1fr] items-center gap-3 px-3 h-9 border-b divider bg-ink-900/60 text-2xs uppercase tracking-wider text-ink-500">
        <span>ID</span>
        <span>Display name</span>
        <span>Role</span>
        <span className="text-right">T / S</span>
        <span className="text-right">Hours</span>
        <span>Voice type</span>
      </div>
      <div className="overflow-y-auto">
        {persons.map((p) => (
          <button
            key={p.id}
            onClick={() => onSelect(p.id)}
            className={cn(
              'w-full text-left grid grid-cols-[140px_1fr_90px_80px_80px_1fr] items-center gap-3 px-3 h-10 border-b divider transition-colors',
              selectedId === p.id ? 'bg-accent/[0.08]' : 'hover:bg-white/[0.025]',
            )}
          >
            <span className="font-mono text-2xs text-ink-400 truncate">{p.id}</span>
            <span className="text-sm text-ink-50 truncate">{p.displayName}</span>
            <span><RoleBadge role={p.role} /></span>
            <span className="text-xs font-mono tabular-nums text-ink-300 text-right">
              {p.sessionsTeacher}/{p.sessionsStudent}
            </span>
            <span className="text-xs font-mono tabular-nums text-ink-300 text-right">
              {p.totalHours.toFixed(1)}
            </span>
            <span className="text-xs text-ink-400 truncate">{p.voiceType || '—'}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
