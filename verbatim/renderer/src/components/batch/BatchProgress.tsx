import { Clock, CheckCircle2, Files } from 'lucide-react';
import { ProgressBar } from '../ui/ProgressBar';
import { fmtEta } from '../../lib/format';

interface Props {
  total: number;
  completed: number;
  currentFile?: string;
  elapsedSec: number;
}

export function BatchProgress({ total, completed, currentFile, elapsedSec }: Props) {
  const pct = total > 0 ? completed / total : 0;
  const avgPerFile = completed > 0 ? elapsedSec / completed : 0;
  const remainingFiles = Math.max(0, total - completed);
  const eta = avgPerFile > 0 ? avgPerFile * remainingFiles : 0;

  return (
    <div className="surface-2 hairline rounded-lg px-4 py-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-xs text-ink-200">
            <Files size={12} className="text-accent" />
            <span className="font-mono tabular-nums">
              <span className="text-ink-50 font-semibold">{completed}</span>
              <span className="text-ink-500"> / {total}</span>
            </span>
            <span className="text-ink-400">files</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-ink-200">
            <span className="font-mono tabular-nums text-ink-50 font-semibold">
              {(pct * 100).toFixed(0)}%
            </span>
          </div>
          {currentFile && (
            <div className="flex items-center gap-1.5 text-xs text-ink-400 min-w-0">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulseSoft" />
              <span className="font-mono truncate max-w-[360px]">{currentFile}</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-4 text-2xs text-ink-400 font-mono tabular-nums">
          <span className="flex items-center gap-1">
            <Clock size={11} />
            elapsed {fmtEta(elapsedSec)}
          </span>
          <span className="flex items-center gap-1 text-accent">
            <CheckCircle2 size={11} />
            ETA {fmtEta(eta)}
          </span>
        </div>
      </div>
      <ProgressBar value={pct} height={6} pulse />
    </div>
  );
}
