import type { DaemonStatus } from './types';

export function deriveTopBarStatus(status: DaemonStatus, running: boolean): DaemonStatus {
  if (!running) {
    return status;
  }
  if (status === 'down' || status === 'shutting_down' || status === 'crashed') {
    return status;
  }
  return 'busy';
}
