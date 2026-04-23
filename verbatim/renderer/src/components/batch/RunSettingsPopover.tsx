import { ChevronDown, Sliders } from 'lucide-react';
import { Popover } from '../ui/Popover';
import { Select } from '../ui/Select';
import { Toggle } from '../ui/Toggle';
import { RunOptions } from '../../types';

interface Props {
  value: RunOptions;
  onChange: (v: RunOptions) => void;
}

const WHISPER_MODELS = [
  { value: 'tiny', label: 'tiny', description: 'fastest, lowest quality' },
  { value: 'base', label: 'base', description: 'fast' },
  { value: 'small', label: 'small', description: 'balanced' },
  { value: 'medium', label: 'medium', description: 'higher quality' },
  { value: 'large', label: 'large', description: 'slow, top accuracy' },
  { value: 'large-v3-turbo', label: 'large-v3-turbo', description: 'recommended default' },
];

const LANGUAGES = [
  { value: 'auto', label: 'Auto-detect' },
  { value: 'en', label: 'English' },
  { value: 'ro', label: 'Romanian' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'de', label: 'German' },
  { value: 'it', label: 'Italian' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'nl', label: 'Dutch' },
  { value: 'sv', label: 'Swedish' },
];

const POLISH = [
  { value: 'off', label: 'Off' },
  { value: 'cli', label: 'CLI' },
  { value: 'claude', label: 'Claude API' },
];

export function RunSettingsPopover({ value, onChange }: Props) {
  return (
    <Popover
      trigger={(open) => (
        <button
          className="h-8 px-2 rounded border border-l-0 border-ink-600/60 bg-accent/80 hover:bg-accent text-white transition-colors btn-focus flex items-center"
          aria-label="Run settings"
          aria-expanded={open}
        >
          <ChevronDown size={14} />
        </button>
      )}
    >
      {() => (
        <div className="p-3">
          <div className="flex items-center gap-2 pb-2 mb-2 border-b divider">
            <Sliders size={13} className="text-accent" />
            <span className="text-xs font-semibold text-ink-100">Run settings</span>
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">Whisper model</label>
              <Select
                value={value.whisper_model}
                onChange={(v) => onChange({ ...value, whisper_model: v as any })}
                options={WHISPER_MODELS}
              />
            </div>

            <div>
              <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">Language</label>
              <Select
                value={value.language}
                onChange={(v) => onChange({ ...value, language: v })}
                options={LANGUAGES}
              />
            </div>

            <div>
              <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">Polish engine</label>
              <Select
                value={value.polish}
                onChange={(v) => onChange({ ...value, polish: v as any })}
                options={POLISH}
              />
            </div>

            <div className="pt-1 border-t divider">
              <Toggle
                checked={value.skip_isolation}
                onChange={(v) => onChange({ ...value, skip_isolation: v })}
                label="Skip vocal isolation"
                description="For already-clean audio"
              />
              <Toggle
                checked={value.skip_diarization}
                onChange={(v) => onChange({ ...value, skip_diarization: v })}
                label="Skip speaker diarization"
                description="For single-speaker recordings"
              />
            </div>
          </div>
        </div>
      )}
    </Popover>
  );
}
