import { Modal } from '../ui/Modal';
import { RedoView } from '../redo/RedoView';

export function RedoPanel({
  open,
  onClose,
  running,
  setRunning,
  pushToast,
}: {
  open: boolean;
  onClose: () => void;
  running: boolean;
  setRunning: (value: boolean) => void;
  pushToast: (toast: { kind: 'error' | 'warning' | 'info'; title: string; body?: string }) => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title='Redo'
      description='Queue a repair pass for low-confidence or mismatched transcript slices from the shell tools rail.'
      width='max-w-5xl'
    >
      <div className='shell-modal-body shell-modal-surface'>
        <RedoView running={running} setRunning={setRunning} pushToast={pushToast} />
      </div>
    </Modal>
  );
}
