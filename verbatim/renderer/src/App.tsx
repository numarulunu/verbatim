import { useCallback, useEffect, useState } from 'react';
import { TitleBar } from './components/shell/TitleBar';
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
import type { DaemonStatus, Toast, UpdateStatus } from './types';

function shouldShowUpdateBanner(next: UpdateStatus | null) {
  return Boolean(next && next.kind !== 'checking' && next.kind !== 'current');
}

export default function App() {
  const [status, setStatus] = useState<DaemonStatus>('down');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [registryOpen, setRegistryOpen] = useState(false);
  const [redoOpen, setRedoOpen] = useState(false);
  const [showBanner, setShowBanner] = useState(false);
  const [settingsRevision, setSettingsRevision] = useState(0);
  const [updateState, setUpdateState] = useState<UpdateStatus | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

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
      if (event.type === 'error') {
        const tail = event.stderr_tail;
        const body = tail
          ? `${event.body ?? ''}\n\n— stderr tail —\n${tail.slice(-1000)}`.trimStart()
          : event.body;
        pushToast({ kind: 'error', title: event.title || 'Error', body });
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
        batchStartedAt={workspace.batchStartedAt}
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
