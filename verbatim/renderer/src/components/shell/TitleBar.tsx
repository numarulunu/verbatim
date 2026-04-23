import { Minus, Square, X, AudioLines } from 'lucide-react';
import { verbatimClient } from '../../bridge/verbatimClient';

function ControlButton({
  label,
  danger = false,
  onClick,
  children,
}: {
  label: string;
  danger?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type='button'
      aria-label={label}
      title={label}
      onClick={onClick}
      className={[
        'app-no-drag flex h-[28px] w-8 items-center justify-center rounded-[4px] border transition-colors',
        danger
          ? 'border-transparent text-ink-400 hover:border-red-500/80 hover:bg-red-500 hover:text-white'
          : 'border-transparent text-ink-400 hover:border-white/[0.08] hover:bg-white/[0.06] hover:text-ink-100',
      ].join(' ')}
    >
      {children}
    </button>
  );
}

export function TitleBar() {
  return (
    <header className='app-drag shell-titlebar'>
      <div className='shell-titlebar__brand'>
        <div className='shell-titlebar__logo'>
          <AudioLines size={12} className='text-emerald-300' />
        </div>
        <div className='shell-titlebar__name'>Verbatim</div>
      </div>

      <div className='shell-titlebar__controls app-no-drag'>
        <ControlButton label='Minimize' onClick={() => { void verbatimClient.minimizeWindow(); }}>
          <Minus size={13} strokeWidth={1.6} />
        </ControlButton>
        <ControlButton label='Maximize' onClick={() => { void verbatimClient.toggleMaximizeWindow(); }}>
          <Square size={11} strokeWidth={1.6} />
        </ControlButton>
        <ControlButton label='Close' danger onClick={() => { void verbatimClient.closeWindow(); }}>
          <X size={13} strokeWidth={1.6} />
        </ControlButton>
      </div>
    </header>
  );
}
