import { FolderOpen } from 'lucide-react';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';

interface Props {
  label: string;
  value: string;
  onBrowse: () => void;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function FolderPicker({ label, value, onBrowse, onChange, disabled }: Props) {
  return (
    <div className="flex-1 min-w-0">
      <label className="text-2xs uppercase tracking-wider text-ink-500 mb-1 block">{label}</label>
      <div className="flex items-stretch">
        <div className="flex-1 min-w-0">
          <Input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            mono
            placeholder="Type or paste a folder path"
            className="rounded-r-none border-r-0"
          />
        </div>
        <Button
          variant="secondary"
          size="md"
          onClick={onBrowse}
          disabled={disabled}
          className="rounded-l-none border-l-0"
          leftIcon={<FolderOpen size={13} />}
        >
          Browse
        </Button>
      </div>
    </div>
  );
}