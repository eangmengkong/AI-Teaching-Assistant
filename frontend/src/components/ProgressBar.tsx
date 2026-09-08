const COLOR_CLASSES = {
  indigo: 'bg-indigo-500',
  emerald: 'bg-emerald-500',
  gradient: 'bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500',
} as const;

type Color = keyof typeof COLOR_CLASSES;

interface ProgressBarProps {
  /** Numeric 0-100, or a pre-formatted string like "42%". */
  value: number | string;
  color?: Color;
  className?: string;
}

/** Skeleton-free progress bar kept small and reusable across the app. */
export default function ProgressBar({ value, color = 'indigo', className = '' }: ProgressBarProps) {
  const width = typeof value === 'number' ? `${Math.min(100, Math.max(0, value))}%` : value;

  return (
    <div className={`h-2 w-full overflow-hidden rounded-full bg-app-surface-2 ${className}`}>
      <div
        className={`h-full rounded-full shadow-sm transition-all duration-500 ${COLOR_CLASSES[color]} ${
          color === 'gradient' ? 'animate-gradient' : ''
        }`}
        style={{ width }}
      />
    </div>
  );
}