import { FolderOpen, RefreshCw } from 'lucide-react';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';

function PathRow({
  label,
  value,
  onChange,
  onBrowse,
  disabled,
  utility,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBrowse: () => void;
  disabled?: boolean;
  utility?: React.ReactNode;
}) {
  return (
    <div className='shell-header__row'>
      <div className='shell-header__label'>{label}</div>
      <div className='shell-header__field'>
        <FolderOpen size={13} className='text-ink-500' />
        <Input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder='Select a folder'
          className='shell-header__input'
          disabled={disabled}
        />
      </div>
      <Button size='sm' onClick={onBrowse} disabled={disabled}>Browse</Button>
      {utility}
    </div>
  );
}

export function WorkspaceHeader({
  inputDir,
  outputDir,
  setInputDir,
  setOutputDir,
  browseInput,
  browseOutput,
  scan,
  refresh,
  openOutput,
  running,
}: {
  inputDir: string;
  outputDir: string;
  setInputDir: (value: string) => void;
  setOutputDir: (value: string) => void;
  browseInput: () => Promise<void>;
  browseOutput: () => Promise<void>;
  scan: () => Promise<void>;
  refresh: () => Promise<void>;
  openOutput: () => Promise<void>;
  running: boolean;
}) {
  const refreshFolders = refresh ?? scan;

  return (
    <section className='shell-header'>
      <div className='shell-header__paths'>
        <PathRow label='Input' value={inputDir} onChange={setInputDir} onBrowse={() => { void browseInput(); }} disabled={running} />
        <PathRow
          label='Output'
          value={outputDir}
          onChange={setOutputDir}
          onBrowse={() => { void browseOutput(); }}
          disabled={running}
          utility={(
            <button
              type='button'
              className='shell-header__utility'
              aria-label='Refresh folders'
              title='Refresh / re-scan folders'
              onClick={() => { void refreshFolders(); }}
              disabled={running}
            >
              <RefreshCw size={13} strokeWidth={1.6} />
            </button>
          )}
        />
      </div>
    </section>
  );
}
