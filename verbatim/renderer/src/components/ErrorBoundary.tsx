import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
  componentStack: string | null;
}

/**
 * Root error boundary for the renderer.
 *
 * Without this, a render-time throw anywhere in the tree unmounts the whole
 * app — black window, no recovery path, no toast (Toasts live inside App).
 * The fallback renders the error with a Copy Details button so the user can
 * paste into a bug report, and a Reload button that requests a full window
 * reload via location.reload().
 *
 * Errors also surface in the main-process log file: main.js redirects
 * console.error to the log sink, and getDerivedStateFromError → console.error
 * is a well-known React contract.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, componentStack: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    this.setState({ componentStack: info.componentStack ?? null });
    // eslint-disable-next-line no-console
    console.error('[renderer] uncaught render error:', error, info.componentStack);
  }

  copyDetails = () => {
    const { error, componentStack } = this.state;
    if (!error) return;
    const text = [
      `${error.name}: ${error.message}`,
      '',
      error.stack ?? '(no stack)',
      '',
      '--- component stack ---',
      componentStack ?? '(unavailable)',
    ].join('\n');
    navigator.clipboard?.writeText(text).catch(() => { /* best-effort */ });
  };

  reload = () => {
    window.location.reload();
  };

  render() {
    const { error, componentStack } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="fixed inset-0 z-[9999] flex items-center justify-center p-8 bg-ink-950 text-ink-50">
        <div className="w-full max-w-2xl rounded-lg border border-red-500/40 bg-red-500/[0.04] p-6">
          <div className="text-lg font-semibold text-red-200 mb-2">Something broke in the UI</div>
          <div className="text-sm text-ink-300 mb-4">
            The renderer hit an uncaught error. Your batch state and settings are untouched. Reload to recover.
          </div>

          <div className="rounded bg-ink-900 border border-ink-700 p-3 mb-4">
            <div className="text-xs font-mono text-red-300 break-words mb-2">
              {error.name}: {error.message}
            </div>
            {error.stack && (
              <pre className="text-2xs font-mono text-ink-400 whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
                {error.stack}
              </pre>
            )}
            {componentStack && (
              <>
                <div className="text-2xs text-ink-500 mt-3 mb-1">— component stack —</div>
                <pre className="text-2xs font-mono text-ink-400 whitespace-pre-wrap break-words max-h-32 overflow-y-auto">
                  {componentStack}
                </pre>
              </>
            )}
          </div>

          <div className="flex gap-2">
            <button
              onClick={this.copyDetails}
              className="h-8 px-3 rounded text-xs border border-ink-600 text-ink-100 hover:bg-white/[0.04]"
            >
              Copy details
            </button>
            <button
              onClick={this.reload}
              className="h-8 px-3 rounded text-xs bg-accent text-ink-950 hover:bg-accent/90 font-medium"
            >
              Reload
            </button>
          </div>
        </div>
      </div>
    );
  }
}
