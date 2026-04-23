import { AlertCircle, CheckCircle2, Download, X } from 'lucide-react';
import type { UpdateStatus } from '../types';

function bannerCopy(status: UpdateStatus) {
  if (status.kind === 'downloaded') {
    return {
      icon: <CheckCircle2 size={12} className="text-accent" />,
      text: `Update ${status.version ?? ''} downloaded. It will install when you quit the app.`.trim(),
    };
  }

  if (status.kind === 'downloading') {
    const percent = typeof status.percent === 'number' ? `${Math.round(status.percent)}%` : 'in progress';
    return {
      icon: <Download size={12} className="text-accent" />,
      text: `Downloading update ${status.version ?? ''} ${percent}`.trim(),
    };
  }

  if (status.kind === 'available') {
    return {
      icon: <Download size={12} className="text-accent" />,
      text: `Update ${status.version ?? ''} available. Download started in the background.`.trim(),
    };
  }

  if (status.kind === 'current') {
    return {
      icon: <CheckCircle2 size={12} className="text-accent" />,
      text: 'App is up to date.',
    };
  }

  if (status.kind === 'error') {
    return {
      icon: <AlertCircle size={12} className="text-warning" />,
      text: status.message || 'Update check failed.',
    };
  }

  return {
    icon: <Download size={12} className="text-accent" />,
    text: 'Checking for updates...',
  };
}

export function UpdateBanner({ status, onDismiss }: { status: UpdateStatus; onDismiss: () => void }) {
  const banner = bannerCopy(status);

  return (
    <div className="h-7 shrink-0 flex items-center justify-center gap-3 text-xs px-3 bg-accent/[0.09] border-b border-accent/20">
      {banner.icon}
      <span className="text-ink-100">{banner.text}</span>
      <button
        onClick={onDismiss}
        className="ml-2 text-ink-500 hover:text-ink-100 p-0.5 rounded hover:bg-white/[0.05]"
      >
        <X size={11} />
      </button>
    </div>
  );
}
