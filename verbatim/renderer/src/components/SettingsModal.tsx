import { useEffect, useState } from 'react';
import { Key, Folder, Sliders, Wrench, RefreshCw, Eye, EyeOff, FileText } from 'lucide-react';
import { Modal } from './ui/Modal';
import { Input } from './ui/Input';
import { Button } from './ui/Button';
import { Select } from './ui/Select';
import { cn } from '../lib/cn';
import { verbatimClient } from '../bridge/verbatimClient';
import { DEFAULT_RENDERER_SETTINGS } from '../bridge/normalize';

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved?: () => void;
  pushToast: (t: { kind: 'error' | 'warning' | 'info'; title: string; body?: string }) => void;
}

type Section = 'keys' | 'paths' | 'defaults' | 'advanced';

const SECTIONS: { id: Section; label: string; icon: React.ReactNode }[] = [
  { id: 'keys', label: 'API keys', icon: <Key size={13} /> },
  { id: 'paths', label: 'Default paths', icon: <Folder size={13} /> },
  { id: 'defaults', label: 'Run defaults', icon: <Sliders size={13} /> },
  { id: 'advanced', label: 'Advanced', icon: <Wrench size={13} /> },
];

function PasswordInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input
        type={show ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        mono
        className="pr-8"
      />
      <button
        type="button"
        onClick={() => setShow((v) => !v)}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-500 hover:text-ink-200"
      >
        {show ? <EyeOff size={13} /> : <Eye size={13} />}
      </button>
    </div>
  );
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div>
      <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">{label}</label>
      {children}
      {hint && <p className="text-2xs text-ink-500 mt-1">{hint}</p>}
    </div>
  );
}

export function SettingsModal({ open, onClose, onSaved, pushToast }: Props) {
  const [section, setSection] = useState<Section>('keys');
  const [hf, setHf] = useState(DEFAULT_RENDERER_SETTINGS.hf);
  const [anth, setAnth] = useState(DEFAULT_RENDERER_SETTINGS.anth);
  const [defInput, setDefInput] = useState(DEFAULT_RENDERER_SETTINGS.defInput);
  const [defOutput, setDefOutput] = useState(DEFAULT_RENDERER_SETTINGS.defOutput);
  const [model, setModel] = useState(DEFAULT_RENDERER_SETTINGS.model);
  const [lang, setLang] = useState(DEFAULT_RENDERER_SETTINGS.lang);
  const [polish, setPolish] = useState(DEFAULT_RENDERER_SETTINGS.polish);
  const [dataDir, setDataDir] = useState(DEFAULT_RENDERER_SETTINGS.dataDir);

  useEffect(() => {
    if (!open) {
      return;
    }

    let alive = true;
    verbatimClient.getSettings().then((settings) => {
      if (!alive) {
        return;
      }
      setHf(settings.hf);
      setAnth(settings.anth);
      setDefInput(settings.defInput);
      setDefOutput(settings.defOutput);
      setModel(settings.model);
      setLang(settings.lang);
      setPolish(settings.polish);
      setDataDir(settings.dataDir);
    }).catch((error) => {
      if (alive) {
        pushToast({
          kind: 'error',
          title: 'Settings failed to load',
          body: error instanceof Error ? error.message : 'Could not load saved settings.',
        });
      }
    });

    return () => {
      alive = false;
    };
  }, [open, pushToast]);

  const save = async () => {
    try {
      await verbatimClient.saveSettings({ hf, anth, defInput, defOutput, model, lang, polish, dataDir });
      onSaved?.();
      pushToast({ kind: 'info', title: 'Settings saved' });
      onClose();
    } catch (error) {
      pushToast({
        kind: 'error',
        title: 'Settings save failed',
        body: error instanceof Error ? error.message : 'Could not save settings.',
      });
    }
  };

  const restart = async () => {
    pushToast({ kind: 'warning', title: 'Restarting daemon...' });
    try {
      await verbatimClient.restart();
      pushToast({ kind: 'info', title: 'Daemon restarted' });
    } catch (error) {
      pushToast({
        kind: 'error',
        title: 'Daemon restart failed',
        body: error instanceof Error ? error.message : 'Could not restart the daemon.',
      });
    }
  };

  const openLogs = async () => {
    try {
      const result = await verbatimClient.openLogsFolder();
      if (!result.ok) {
        pushToast({
          kind: 'warning',
          title: 'Could not open logs folder',
          body: result.error ?? 'Unknown error.',
        });
      }
    } catch (error) {
      pushToast({
        kind: 'error',
        title: 'Logs folder unavailable',
        body: error instanceof Error ? error.message : 'Bridge not ready.',
      });
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Settings"
      width="max-w-3xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={save}>Save</Button>
        </>
      }
    >
      <div className="grid grid-cols-[160px_1fr] gap-5 -mt-1">
        <nav className="flex flex-col gap-0.5">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              onClick={() => setSection(s.id)}
              className={cn(
                'flex items-center gap-2 h-8 px-2.5 rounded text-sm transition-colors text-left',
                section === s.id
                  ? 'bg-accent-soft text-accent'
                  : 'text-ink-300 hover:text-ink-50 hover:bg-white/[0.04]',
              )}
            >
              <span className="opacity-90">{s.icon}</span>
              {s.label}
            </button>
          ))}
        </nav>

        <div className="min-h-[340px]">
          {section === 'keys' && (
            <div className="space-y-4">
              <Field
                label="HUGGINGFACE_TOKEN"
                hint="Required for pyannote speaker diarization models."
              >
                <PasswordInput value={hf} onChange={setHf} placeholder="hf_..." />
              </Field>
              <Field
                label="ANTHROPIC_API_KEY"
                hint="Used only when polish engine = Claude API."
              >
                <PasswordInput value={anth} onChange={setAnth} placeholder="sk-ant-..." />
              </Field>
              <div className="rounded bg-ink-850 border divider p-3 text-xs text-ink-400 flex gap-2">
                <span className="text-accent">i</span>
                Keys are stored in the app settings on this machine.
              </div>
            </div>
          )}

          {section === 'paths' && (
            <div className="space-y-4">
              <Field label="Default input folder">
                <Input value={defInput} onChange={(e) => setDefInput(e.target.value)} mono />
              </Field>
              <Field label="Default output folder">
                <Input value={defOutput} onChange={(e) => setDefOutput(e.target.value)} mono />
              </Field>
            </div>
          )}

          {section === 'defaults' && (
            <div className="space-y-4">
              <Field label="Whisper model">
                <Select
                  value={model}
                  onChange={setModel}
                  options={[
                    { value: 'tiny', label: 'tiny' },
                    { value: 'base', label: 'base' },
                    { value: 'small', label: 'small' },
                    { value: 'medium', label: 'medium' },
                    { value: 'large', label: 'large' },
                    { value: 'large-v3-turbo', label: 'large-v3-turbo (recommended)' },
                  ]}
                />
              </Field>
              <Field label="Default language">
                <Select
                  value={lang}
                  onChange={setLang}
                  options={[
                    { value: 'auto', label: 'Auto-detect' },
                    { value: 'en', label: 'English' },
                    { value: 'ro', label: 'Romanian' },
                    { value: 'es', label: 'Spanish' },
                    { value: 'fr', label: 'French' },
                    { value: 'de', label: 'German' },
                    { value: 'it', label: 'Italian' },
                  ]}
                />
              </Field>
              <Field label="Polish engine">
                <Select
                  value={polish}
                  onChange={setPolish}
                  options={[
                    { value: 'off', label: 'Off' },
                    { value: 'cli', label: 'CLI' },
                    { value: 'claude', label: 'Claude API' },
                  ]}
                />
              </Field>
            </div>
          )}

          {section === 'advanced' && (
            <div className="space-y-4">
              <Field
                label="Data directory"
                hint="Overrides VERBATIM_ROOT. Stores models, registry, corpus."
              >
                <Input value={dataDir} onChange={(e) => setDataDir(e.target.value)} mono />
              </Field>
              <div className="pt-2 border-t divider">
                <div className="flex items-start gap-3">
                  <div className="flex-1">
                    <div className="text-sm text-ink-100">Restart daemon</div>
                    <div className="text-xs text-ink-400 mt-0.5">
                      Useful after changing API keys or data directory.
                    </div>
                  </div>
                  <Button variant="secondary" leftIcon={<RefreshCw size={12} />} onClick={restart}>
                    Restart
                  </Button>
                </div>
              </div>
              <div className="pt-2 border-t divider">
                <div className="flex items-start gap-3">
                  <div className="flex-1">
                    <div className="text-sm text-ink-100">Open logs folder</div>
                    <div className="text-xs text-ink-400 mt-0.5">
                      Main-process + daemon stderr logs. Attach when reporting bugs.
                    </div>
                  </div>
                  <Button variant="secondary" leftIcon={<FileText size={12} />} onClick={openLogs}>
                    Open
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
