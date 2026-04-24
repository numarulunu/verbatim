import { AlertCircle, CheckCircle2, Download, X } from 'lucide-react';
import { useState } from 'react';
import type { UpdateStatus } from '../types';
import { verbatimClient } from '../bridge/verbatimClient';

function bannerCopy(status: UpdateStatus) {
  if (status.kind === 'downloaded') {
    return {
      icon: <CheckCircle2 size={12} className="text-accent" />,
      text: `Update ${status.version ?? ''} downloaded and ready to install.`.trim(),
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
  const [installing, setInstalling] = useState(false);

  const install = async () => {
    if (installing) return;
    setInstalling(true);
    try {
      await verbatimClient.installUpdateNow();
      // If install succeeds, the app relaunches and we never get here.
    } catch {
      setInstalling(false);
    }
  };

  return (
    <div className="h-7 shrink-0 flex items-center justify-center gap-3 text-xs px-3 bg-[#171717] border-b border-white/[0.06]">
      {banner.icon}
      <span className="text-ink-200">{banner.text}</span>
      {status.kind === 'downloaded' && (
        <button
          onClick={install}
          disabled={installing}
          className="ml-1 px-2 py-0.5 rounded text-2xs bg-accent/20 text-accent border border-accent/40 hover:bg-accent/30 disabled:opacity-50"
        >
          {installing ? 'Installing...' : 'Install now'}
        </button>
      )}
      <button
        onClick={onDismiss}
        className="ml-2 text-ink-500 hover:text-ink-100 p-0.5 rounded hover:bg-white/[0.05]"
      >
        <X size={11} />
      </button>
    </div>
  );
}
