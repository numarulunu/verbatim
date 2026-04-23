import type { RunOptions } from '../../types';
import { Select } from '../ui/Select';
import { Toggle } from '../ui/Toggle';
import { Button } from '../ui/Button';

function SectionHead({ eyebrow, title, detail }: { eyebrow: string; title: string; detail: string }) {
  return (
    <div className='shell-section__head'>
      <span className='shell-section__eyebrow'>{eyebrow}</span>
      <div>
        <div className='shell-section__title'>{title}</div>
        <p className='shell-section__detail'>{detail}</p>
      </div>
    </div>
  );
}

function MetricBar({ label, value, tone, detail }: { label: string; value: string; tone: string; detail: string }) {
  return (
    <div className='shell-meter'>
      <div className='shell-meter__head'>
        <span>{label}</span>
        <span className={tone}>{value}</span>
      </div>
      <div className='shell-meter__track'>
        <div className={['shell-meter__fill', tone].join(' ')} />
      </div>
      <div className='shell-meter__detail'>{detail}</div>
    </div>
  );
}

export function SettingsRail({
  opts,
  setOpts,
  scanSummary,
  selectedCount,
  running,
  onOpenSettings,
  onOpenRegistry,
  onOpenRedo,
}: {
  opts: RunOptions;
  setOpts: (value: RunOptions) => void;
  scanSummary: { total: number; fresh: number; processed: number };
  selectedCount: number;
  running: boolean;
  onOpenSettings: () => void;
  onOpenRegistry: () => void;
  onOpenRedo: () => void;
}) {
  const selectionRatio = scanSummary.fresh > 0 ? Math.round((selectedCount / scanSummary.fresh) * 100) : 0;
  const polishLabel = opts.polish === 'claude' ? 'Claude' : opts.polish === 'cli' ? 'CLI' : 'Off';

  return (
    <aside className='shell-rail'>
      <div className='shell-rail__top'>
        <div className='shell-rail__preset'>
          <span className='shell-kicker'>Preset</span>
          <div className='shell-rail__preset-shell'>
            <select value='custom' disabled aria-label='Preset shell preview' className='shell-rail__preset-control'>
              <option value='custom'>Custom</option>
            </select>
            <span className='shell-rail__preset-icon' aria-hidden='true'>v</span>
          </div>
        </div>

        <div className='shell-card shell-card--impact'>
          <div className='shell-card__head'>
            <span className='shell-kicker'>Queue</span>
            <span className='text-lg font-semibold text-ink-50'>{scanSummary.total} scanned</span>
          </div>

          <div className='shell-card__stats'>
            <div>
              <span className='shell-kicker'>Selected</span>
              <strong>{selectedCount}</strong>
            </div>
            <div>
              <span className='shell-kicker'>Fresh</span>
              <strong>{scanSummary.fresh}</strong>
            </div>
            <div>
              <span className='shell-kicker'>Processed</span>
              <strong>{scanSummary.processed}</strong>
            </div>
            <div>
              <span className='shell-kicker'>Polish</span>
              <strong>{polishLabel}</strong>
            </div>
          </div>

          <MetricBar label='Selection coverage' value={`${selectionRatio}%`} tone='tone-accent' detail='Focus the next run on fresh files only.' />
          <MetricBar label='Speaker detail' value={opts.skip_diarization ? 'Reduced' : 'Full'} tone='tone-warn' detail='Diarization keeps speakers separated in the transcript.' />
          <MetricBar label='Cleanup pass' value={polishLabel} tone='tone-muted' detail='CLI is local. Claude is slower but can polish phrasing.' />
        </div>
      </div>

      <div className='shell-rail__body'>
        <section className='shell-card shell-card--section'>
          <SectionHead eyebrow='Speech' title='Transcription' detail='Pick the model and language for this run.' />

          <div className='shell-form-block'>
            <label className='shell-label'>Whisper model</label>
            <Select
              value={opts.whisper_model}
              onChange={(value) => setOpts({ ...opts, whisper_model: value as RunOptions['whisper_model'] })}
              options={[
                { value: 'tiny', label: 'tiny' },
                { value: 'base', label: 'base' },
                { value: 'small', label: 'small' },
                { value: 'medium', label: 'medium' },
                { value: 'large', label: 'large' },
                { value: 'large-v3-turbo', label: 'large-v3-turbo' },
              ]}
            />
          </div>

          <div className='shell-form-block'>
            <label className='shell-label'>Language</label>
            <Select
              value={opts.language}
              onChange={(value) => setOpts({ ...opts, language: value })}
              options={[
                { value: 'auto', label: 'Auto detect' },
                { value: 'en', label: 'English' },
                { value: 'ro', label: 'Romanian' },
                { value: 'de', label: 'German' },
                { value: 'fr', label: 'French' },
                { value: 'it', label: 'Italian' },
              ]}
            />
          </div>
        </section>

        <section className='shell-card shell-card--section'>
          <SectionHead eyebrow='Cleanup' title='Polish' detail='Keep Verbatim cleanup controls in the rail, not the popup.' />

          <div className='shell-form-block'>
            <label className='shell-label'>Polish mode</label>
            <Select
              value={opts.polish}
              onChange={(value) => setOpts({ ...opts, polish: value as RunOptions['polish'] })}
              options={[
                { value: 'off', label: 'Off' },
                { value: 'cli', label: 'CLI' },
                { value: 'claude', label: 'Claude API' },
              ]}
            />
          </div>
        </section>

        <section className='shell-card shell-card--section'>
          <SectionHead eyebrow='Audio prep' title='Source shaping' detail='Preserve the isolation and diarization toggles in the main shell.' />

          <Toggle
            checked={!opts.skip_isolation}
            onChange={(value) => setOpts({ ...opts, skip_isolation: !value })}
            label='Source isolation'
            description='Helps pull vocals forward before transcription.'
          />
          <Toggle
            checked={!opts.skip_diarization}
            onChange={(value) => setOpts({ ...opts, skip_diarization: !value })}
            label='Speaker diarization'
            description='Keeps teacher and student segments separated.'
          />
        </section>

        <div className='shell-rail__tools'>
          <Button variant='ghost' size='sm' className='shell-rail__tool-link' onClick={onOpenRegistry} disabled={running}>Registry</Button>
          <Button variant='ghost' size='sm' className='shell-rail__tool-link' onClick={onOpenRedo}>Redo</Button>
          <Button variant='ghost' size='sm' className='shell-rail__tool-link' onClick={onOpenSettings}>Advanced settings</Button>
        </div>
      </div>
    </aside>
  );
}
