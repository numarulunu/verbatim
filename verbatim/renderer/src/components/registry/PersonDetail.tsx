import { Edit3, Pencil, GitMerge, User, FileText } from 'lucide-react';
import { Person } from '../../types';
import { Pill } from '../ui/Pill';
import { Button } from '../ui/Button';
import { fmtSize } from '../../lib/format';

interface Props {
  person?: Person;
  onEdit: () => void;
  onRename: () => void;
  onMerge: () => void;
}

function Field({ label, value }: { label: string; value?: React.ReactNode }) {
  return (
    <div>
      <div className="text-2xs uppercase tracking-wider text-ink-500 mb-1">{label}</div>
      <div className="text-sm text-ink-100">{value || <span className="text-ink-500">—</span>}</div>
    </div>
  );
}

export function PersonDetail({ person, onEdit, onRename, onMerge }: Props) {
  if (!person) {
    return (
      <div className="surface-2 hairline rounded-lg flex items-center justify-center p-8 text-center">
        <div>
          <div className="w-10 h-10 mx-auto mb-3 rounded-full bg-ink-800 flex items-center justify-center">
            <User size={16} className="text-ink-500" />
          </div>
          <p className="text-sm text-ink-300">Select a person to inspect</p>
        </div>
      </div>
    );
  }

  return (
    <div className="surface-2 hairline rounded-lg flex flex-col min-h-0 overflow-hidden">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 border-b divider">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold text-ink-50 truncate">{person.displayName}</h2>
            <div className="text-xs font-mono text-ink-500 mt-0.5">{person.id}</div>
          </div>
          <div className="flex items-center gap-2">
            {person.role === 'teacher' && <Pill tone="accent">teacher</Pill>}
            {person.role === 'student' && <Pill tone="success">student</Pill>}
            {person.role === 'unknown' && <Pill tone="muted">unknown</Pill>}
            {person.bootstrapCounter > 0 && (
              <Pill tone="warning">bootstrap · {person.bootstrapCounter}</Pill>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Field grid */}
        <div className="grid grid-cols-3 gap-x-4 gap-y-4">
          <Field label="Role" value={person.role} />
          <Field label="Voice type" value={person.voiceType} />
          <Field label="Fach" value={person.fach} />
          <Field label="First seen" value={<span className="font-mono text-xs">{person.firstSeen}</span>} />
          <Field label="Last updated" value={<span className="font-mono text-xs">{person.lastUpdated}</span>} />
          <Field
            label="Sessions (T / S)"
            value={
              <span className="font-mono text-xs">
                {person.sessionsTeacher} / {person.sessionsStudent}
              </span>
            }
          />
          <Field label="Total hours" value={<span className="font-mono text-xs">{person.totalHours.toFixed(1)}</span>} />
          <Field
            label="Observed regions"
            value={
              person.observedRegions.length ? (
                <div className="flex flex-wrap gap-1">
                  {person.observedRegions.map((r) => (
                    <Pill key={r} tone="neutral">{r}</Pill>
                  ))}
                </div>
              ) : undefined
            }
          />
          <Field
            label="Bootstrap counter"
            value={<span className="font-mono text-xs">{person.bootstrapCounter}</span>}
          />
        </div>

        {/* Voiceprint files */}
        <div>
          <div className="text-2xs uppercase tracking-wider text-ink-500 mb-2">Voiceprint files</div>
          <div className="surface-3 rounded border divider overflow-hidden">
            {person.voiceprintFiles.map((f) => (
              <div
                key={f.name}
                className="flex items-center justify-between px-3 h-8 border-b divider last:border-0"
              >
                <div className="flex items-center gap-2">
                  <FileText size={12} className="text-ink-500" />
                  <span className="font-mono text-xs text-ink-100">{f.name}</span>
                </div>
                <span className="font-mono text-2xs text-ink-500">{fmtSize(f.bytes)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="px-5 py-3 border-t divider flex items-center gap-2 bg-ink-900/40">
        <Button variant="secondary" leftIcon={<Edit3 size={12} />} onClick={onEdit}>
          Edit
        </Button>
        <Button variant="secondary" leftIcon={<Pencil size={12} />} onClick={onRename}>
          Rename
        </Button>
        <Button variant="secondary" leftIcon={<GitMerge size={12} />} onClick={onMerge}>
          Merge into…
        </Button>
      </div>
    </div>
  );
}
