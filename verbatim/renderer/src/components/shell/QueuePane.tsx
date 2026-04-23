import type { DaemonStatus } from '../../types';
import type { BatchWorkspaceController } from '../../hooks/useBatchWorkspace';
import { FileList } from '../batch/FileList';

function statusLabel(status: DaemonStatus, running: boolean) {
  if (running) return 'Processing';
  if (status === 'ready') return 'Ready';
  if (status === 'spawning') return 'Starting';
  if (status === 'crashed') return 'Crashed';
  if (status === 'shutting_down') return 'Stopping';
  return 'Offline';
}

export function QueuePane({
  workspace,
  status,
}: {
  workspace: BatchWorkspaceController;
  status: DaemonStatus;
}) {
  const doneCount = Object.values(workspace.progress).filter((item) => item.state === 'success').length;
  const failedCount = Object.values(workspace.progress).filter((item) => item.state === 'failed').length;

  return (
    <section className='shell-queue'>
      <header className='shell-queue__head'>
        <div>
          <div className='shell-kicker'>Queue</div>
          <div className='shell-queue__status'>{statusLabel(status, workspace.running)}</div>
        </div>
        <div className='shell-queue__head-meta'>
          <span>{workspace.selection.size} selected</span>
          <span>{workspace.scanSummary.fresh} fresh</span>
        </div>
      </header>

      <div className='shell-queue__body'>
        <FileList
          files={workspace.sortedFiles}
          progress={workspace.progress}
          selection={workspace.selection}
          onToggle={workspace.toggle}
          onToggleAll={workspace.toggleAll}
          running={workspace.running}
          sortKey={workspace.sortKey}
          onSort={workspace.setSortKey}
        />
      </div>

      <footer className='shell-queue__footer'>
        <span><strong>{workspace.scanSummary.total}</strong> total</span>
        <span><strong>{workspace.scanSummary.fresh}</strong> fresh</span>
        <span><strong>{workspace.scanSummary.processed}</strong> processed</span>
        <span><strong>{doneCount}</strong> done</span>
        <span><strong>{failedCount}</strong> failed</span>
      </footer>
    </section>
  );
}
