import { Modal } from '../ui/Modal';
import { RegistryView } from '../registry/RegistryView';

export function RegistryPanel({
  open,
  onClose,
  pushToast,
}: {
  open: boolean;
  onClose: () => void;
  pushToast: (toast: { kind: 'error' | 'warning' | 'info'; title: string; body?: string }) => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title='Registry'
      description='Manage known people, naming collisions, and profile metadata from the shell tools rail.'
      width='max-w-6xl'
    >
      <div className='shell-modal-body shell-modal-surface'>
        <RegistryView pushToast={pushToast} />
      </div>
    </Modal>
  );
}
