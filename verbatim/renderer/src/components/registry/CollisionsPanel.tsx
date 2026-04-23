import { AlertTriangle } from 'lucide-react';
import { Collision, Person } from '../../types';

interface Props {
  collisions: Collision[];
  persons: Person[];
}

export function CollisionsPanel({ collisions, persons }: Props) {
  if (collisions.length === 0) return null;
  const byId = new Map(persons.map((p) => [p.id, p]));

  return (
    <div className="surface-2 hairline rounded-lg border-l-2 border-l-amber-500/70 overflow-hidden">
      <div className="flex items-center gap-2 px-3 h-9 border-b divider bg-amber-500/[0.06]">
        <AlertTriangle size={13} className="text-amber-400" />
        <span className="text-xs font-semibold text-ink-100">Voiceprint collisions</span>
        <span className="text-2xs text-ink-500 font-mono">{collisions.length} detected</span>
      </div>
      <div className="divide-y divider">
        {collisions.map((c, i) => {
          const a = byId.get(c.a);
          const b = byId.get(c.b);
          const score = c.similarity;
          const high = score > 0.9;
          return (
            <div key={i} className="flex items-center gap-3 px-3 h-10">
              <span className="text-xs text-ink-100 flex-1 truncate">
                {a?.displayName ?? c.a}
              </span>
              <span className="text-xs text-ink-500">↔</span>
              <span className="text-xs text-ink-100 flex-1 truncate">
                {b?.displayName ?? c.b}
              </span>
              <span
                className={`font-mono text-xs tabular-nums ${
                  high ? 'text-amber-300' : 'text-ink-300'
                }`}
              >
                {score.toFixed(3)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
