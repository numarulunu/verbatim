import type { DaemonStatus } from '../../types';
import type { BatchWorkspaceController } from '../../hooks/useBatchWorkspace';
import { FileList } from '../batch/FileList';
import { WorkspaceHeader } from './WorkspaceHeader';

export function QueuePane({
  workspace,
}: {
  workspace: BatchWorkspaceController;
  status: DaemonStatus;
}) {
  return (
    <section className='shell-queue'>
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
    </section>
  );
}
