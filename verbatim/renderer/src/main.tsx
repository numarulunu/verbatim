import ReactDOM from 'react-dom/client';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import './index.css';

// StrictMode intentionally removed (SMAC 2026-04-23 Finding 11). Its dev-only
// double-mount races with batchPathState, a module-level singleton in the
// IPC bridge: the second subscription's batchPathState.clear() on
// batch_complete can fire while the first subscription is still delivering
// phase events with the old path map. The Electron renderer is single-
// purpose (no SSR, no hydration), so the correctness value StrictMode adds
// in web apps does not apply here. Revisit if we ever add concurrent-mode
// features (useTransition, startTransition).
ReactDOM.createRoot(document.getElementById('root')!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
