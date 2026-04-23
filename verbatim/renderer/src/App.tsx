import { useCallback, useEffect, useState } from 'react';
import { TitleBar } from './components/shell/TitleBar';
import { WorkspaceHeader } from './components/shell/WorkspaceHeader';
import { QueuePane } from './components/shell/QueuePane';
import { SettingsRail } from './components/shell/SettingsRail';
import { BottomActionBar } from './components/shell/BottomActionBar';
import { RegistryPanel } from './components/shell/RegistryPanel';
import { RedoPanel } from './components/shell/RedoPanel';
import { SettingsModal } from './components/SettingsModal';
import { Toasts } from './components/Toasts';
import { UpdateBanner } from './components/UpdateBanner';
import { verbatimClient } from './bridge/verbatimClient';
import { useBatchWorkspace } from './hooks/useBatchWorkspace';
import type { DaemonStatus, ResourceStats, Toast, UpdateStatus } from './types';

function shouldShowUpdateBanner(next: UpdateStatus | null) {
  return Boolean(next && next.kind !== 'checking' && next.kind !== 'current');
}

const DEFAULT_STATS: ResourceStats = {
  cpu_pct: 6,
  gpu_pct: 1,
  gpu_mem_used_gb: 1.4,
  gpu_mem_total_gb: 24,
  ram_used_gb: 8.1,
  ram_total_gb: 32,
  disk_free_gb: 482,
};

export default function App() {
  const [status, setStatus] = useState<DaemonStatus>('down');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [registryOpen, setRegistryOpen] = useState(false);
  const [redoOpen, setRedoOpen] = useState(false);
  const [showBanner, setShowBanner] = useState(false);
  const [settingsRevision, setSettingsRevision] = useState(0);
  const [updateState, setUpdateState] = useState<UpdateStatus | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [stats, setStats] = useState<ResourceStats>(DEFAULT_STATS);

  const pushToast = useCallback((toast: { kind: 'error' | 'warning' | 'info'; title: string; body?: string }) => {
    setToasts((current) => [...current, { ...toast, id: Math.random().toString(36).slice(2) }]);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const workspace = useBatchWorkspace({ settingsRevision, pushToast });

  useEffect(() => {
    let alive = true;

    verbatimClient.status().then((next) => {
      if (alive) {
        setStatus(next);
      }
    }).catch(() => {});

    verbatimClient.updateStatus().then((next) => {
      if (alive) {
        setUpdateState(next ?? null);
        setShowBanner(shouldShowUpdateBanner(next ?? null));
      }
    }).catch(() => {});

    const offStatus = verbatimClient.onStatus((next) => setStatus(next));
    const offUpdate = verbatimClient.onUpdateStatus((payload: unknown) => {
      const next = payload as UpdateStatus | null;
      setUpdateState(next ?? null);
      setShowBanner(shouldShowUpdateBanner(next));
    });
    const offEvent = verbatimClient.onEvent((event) => {
      if (event.type === 'batch_complete') {
        pushToast({ kind: 'info', title: 'Batch complete', body: 'All queued files finished.' });
      }
      if (event.type === 'cancel_accepted') {
        pushToast({ kind: 'warning', title: 'Batch cancelled', body: 'Pending files were left untouched.' });
      }
      if (event.type === 'resource_stats') {
        setStats({
          cpu_pct: event.cpu_pct,
          gpu_pct: event.gpu_pct,
          gpu_mem_used_gb: event.gpu_mem_used_gb,
          gpu_mem_total_gb: event.gpu_mem_total_gb,
          ram_used_gb: event.ram_used_gb,
          ram_total_gb: event.ram_total_gb,
          disk_free_gb: event.disk_free_gb,
        });
      }
      if (event.type === 'error') {
        pushToast({ kind: 'error', title: event.title || 'Error', body: event.body });
      }
      if (event.type === 'warning') {
        pushToast({ kind: 'warning', title: event.title || 'Warning', body: event.body });
      }
    });

    return () => {
      alive = false;
      offStatus();
      offUpdate();
      offEvent();
    };
  }, [pushToast]);

  return (
    <div className='shell-app'>
      {showBanner && updateState ? <UpdateBanner status={updateState} onDismiss={() => setShowBanner(false)} /> : null}

      <TitleBar />

      <WorkspaceHeader
        inputDir={workspace.inputDir}
        outputDir={workspace.outputDir}
        setInputDir={workspace.setInputDir}
        setOutputDir={workspace.setOutputDir}
        browseInput={workspace.browseInput}
        browseOutput={workspace.browseOutput}
        scan={workspace.scan}
        refresh={workspace.refresh}
        openOutput={workspace.openOutput}
        running={workspace.running}
      />

      <main className='shell-main'>
        <QueuePane workspace={workspace} status={status} />
        <SettingsRail
          opts={workspace.opts}
          setOpts={workspace.setOpts}
          scanSummary={workspace.scanSummary}
          selectedCount={workspace.selection.size}
          running={workspace.running}
          onOpenSettings={() => setSettingsOpen(true)}
          onOpenRegistry={() => setRegistryOpen(true)}
          onOpenRedo={() => setRedoOpen(true)}
        />
      </main>

      <BottomActionBar
        running={workspace.running}
        status={status}
        selectedCount={workspace.selection.size}
        completedCount={workspace.completedCount}
        elapsed={workspace.elapsed}
        stats={stats}
        onStart={workspace.start}
        onCancel={workspace.cancel}
        onOpenOutput={workspace.openOutput}
      />

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={() => setSettingsRevision((value) => value + 1)}
        pushToast={pushToast}
      />

      <RegistryPanel open={registryOpen} onClose={() => setRegistryOpen(false)} pushToast={pushToast} />
      <RedoPanel
        open={redoOpen}
        onClose={() => setRedoOpen(false)}
        running={workspace.running}
        setRunning={workspace.setRunning}
        pushToast={pushToast}
      />

      <Toasts toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
