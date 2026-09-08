const STATUS_STYLES: Record<string, string> = {
  completed: 'border-emerald-500/30 bg-emerald-500/15 text-app-success',
  skipped: 'border-rose-500/30 bg-rose-500/15 text-rose-500',
  rescheduled: 'border-amber-500/30 bg-amber-500/15 text-amber-500',
  planned: 'border-indigo-500/30 bg-indigo-500/15 text-app-accent',
};

const STATUS_DOTS: Record<string, string> = {
  completed: 'bg-emerald-400',
  skipped: 'bg-rose-400',
  rescheduled: 'bg-amber-400',
  planned: 'bg-indigo-400',
};

const DEFAULT_STYLE = 'border-app-border bg-app-hover text-app-soft';
const DEFAULT_DOT = 'bg-app-muted';

/** Colored status pill used for lesson states (planned/completed/skipped/...). */
export default function StatusBadge({ status }: { status: string }) {
  const key = status.toLowerCase();

  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-medium capitalize ${STATUS_STYLES[key] ?? DEFAULT_STYLE}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOTS[key] ?? DEFAULT_DOT}`} aria-hidden />
      {key || 'planned'}
    </span>
  );
}