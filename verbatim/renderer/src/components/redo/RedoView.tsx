import { useEffect, useState } from 'react';
import { Search, Play } from 'lucide-react';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { Toggle } from '../ui/Toggle';
import { verbatimClient } from '../../bridge/verbatimClient';

interface Props {
  running: boolean;
  setRunning: (v: boolean) => void;
  pushToast: (t: { kind: 'error' | 'warning' | 'info'; title: string; body?: string }) => void;
}

export function RedoView({ running, setRunning, pushToast }: Props) {
  const [threshold, setThreshold] = useState('3');
  const [studentId, setStudentId] = useState('');
  const [teacherId, setTeacherId] = useState('');
  const [confidence, setConfidence] = useState('');
  const [afterDate, setAfterDate] = useState('');
  const [ignoreFilter, setIgnoreFilter] = useState(false);
  const [summary, setSummary] = useState<{ session_count: number; persons: number; total_hours: number } | null>(null);

  useEffect(() => {
    let alive = true;

    verbatimClient.getCorpusSummary().catch((error) => {
      if (!alive) {
        return;
      }
      pushToast({
        kind: 'warning',
        title: 'Corpus summary unavailable',
        body: error instanceof Error ? error.message : 'Could not load corpus summary.',
      });
    });

    const off = verbatimClient.onEvent((event) => {
      if (event.type === 'corpus_summary') {
        setSummary({
          session_count: event.session_count,
          persons: Object.keys(event.persons).length,
          total_hours: event.total_hours,
        });
      }
    });

    return () => {
      alive = false;
      off();
    };
  }, [pushToast]);

  const buildFilter = () => {
    const filter: Record<string, unknown> = {};

    if (ignoreFilter) {
      filter.all = true;
      return filter;
    }

    const thresholdValue = Number.parseInt(threshold, 10);
    const confidenceValue = Number.parseFloat(confidence);

    if (Number.isFinite(thresholdValue)) {
      filter.threshold = thresholdValue;
    }
    if (studentId.trim()) {
      filter.student = studentId.trim();
    }
    if (teacherId.trim()) {
      filter.teacher = teacherId.trim();
    }
    if (Number.isFinite(confidenceValue) && confidenceValue > 0) {
      filter.confidence_below = confidenceValue;
    }
    if (afterDate.trim()) {
      filter.after = afterDate.trim();
    }

    return filter;
  };

  const runRedo = async () => {
    const filter = buildFilter();
    const label = ignoreFilter ? 'redo all matching corpus entries' : 'redo the filtered matches';
    const ok = confirm(`Run redo_batch to ${label}? Existing outputs will be overwritten.`);
    if (!ok) return;

    try {
      setRunning(true);
      await verbatimClient.redoBatch(filter);
      pushToast({ kind: 'info', title: 'Redo queued', body: 'Batch view will show progress.' });
    } catch (error) {
      setRunning(false);
      pushToast({
        kind: 'error',
        title: 'Redo failed',
        body: error instanceof Error ? error.message : 'Could not queue the redo batch.',
      });
    }
  };

  return (
    <div className="flex flex-col h-full p-4 gap-3 min-h-0">
      <div className="surface-2 hairline rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <Search size={13} className="text-accent" />
          <span className="text-sm font-semibold text-ink-100">Redo filter</span>
          <div className="ml-auto">
            <Toggle
              checked={ignoreFilter}
              onChange={setIgnoreFilter}
              label="All - ignore filter"
            />
          </div>
        </div>

        <div className={`grid grid-cols-3 gap-x-4 gap-y-3 ${ignoreFilter ? 'opacity-40 pointer-events-none' : ''}`}>
          <div>
            <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">
              Threshold <span className="text-ink-600 normal-case tracking-normal">(sessions below)</span>
            </label>
            <Input
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              type="number"
              mono
              placeholder="3"
            />
          </div>
          <div>
            <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">Student ID</label>
            <Input value={studentId} onChange={(e) => setStudentId(e.target.value)} mono placeholder="spk_..." />
          </div>
          <div>
            <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">Teacher ID</label>
            <Input value={teacherId} onChange={(e) => setTeacherId(e.target.value)} mono placeholder="spk_..." />
          </div>
          <div>
            <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">
              Confidence below <span className="text-ink-600 normal-case tracking-normal">(0-1)</span>
            </label>
            <Input
              value={confidence}
              onChange={(e) => setConfidence(e.target.value)}
              mono
              placeholder="0.85"
            />
          </div>
          <div>
            <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">After date</label>
            <Input value={afterDate} onChange={(e) => setAfterDate(e.target.value)} mono placeholder="2024-01-01" />
          </div>
        </div>

        <div className="flex items-center gap-2 mt-4">
          <Button variant="primary" leftIcon={<Play size={12} fill="currentColor" />} onClick={runRedo} disabled={running}>
            Run redo
          </Button>
          {summary ? (
            <span className="ml-auto text-xs text-ink-400 font-mono">
              {summary.session_count} sessions - {summary.persons} persons - {summary.total_hours.toFixed(1)} hours
            </span>
          ) : (
            <span className="ml-auto text-xs text-ink-500">
              Dry-run candidates are not exposed by this backend.
            </span>
          )}
        </div>
      </div>

      <div className="surface-2 hairline rounded-lg p-4 flex-1 min-h-0 flex items-center justify-center text-center">
        <div>
          <p className="text-sm text-ink-100">Preview slice disabled.</p>
          <p className="text-2xs text-ink-500 mt-1">
            The backend only exposes redo_batch, so the UI runs the batch directly after confirmation.
          </p>
        </div>
      </div>
    </div>
  );
}
