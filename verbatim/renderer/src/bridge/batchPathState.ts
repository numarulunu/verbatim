export function createBatchPathState() {
  let activeFiles: string[] = [];
  let pendingFiles: string[] = [];

  return {
    queue(files: string[]) {
      pendingFiles = files.slice();
    },
    confirm() {
      activeFiles = pendingFiles.slice();
      pendingFiles = [];
    },
    cancelPending() {
      pendingFiles = [];
    },
    clear() {
      activeFiles = [];
      pendingFiles = [];
    },
    resolve(fileIndex: number, fallback?: string) {
      if (fallback) {
        activeFiles[fileIndex] = fallback;
        return fallback;
      }
      return activeFiles[fileIndex] ?? '';
    },
  };
}
