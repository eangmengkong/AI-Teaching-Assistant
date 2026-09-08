import { BookOpen } from 'lucide-react';
import { Pencil } from 'lucide-react';

/**
 * Clickable chip that opens exactly the listed PDF pages for a lesson.
 * Used on the overview, schedule and progress pages.
 */
export default function PagesChip({
  kind,
  spec,
  busy,
  onOpen,
}: {
  kind: 'textbook' | 'workbook';
  spec: string;
  busy: boolean;
  onOpen: () => void;
}) {
  const isTextbook = kind === 'textbook';
  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={busy}
      title={`Open ${kind} pages ${spec} as PDF`}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 font-mono text-xs font-semibold transition disabled:opacity-50 ${
        isTextbook
          ? 'border-indigo-500/40 bg-indigo-500/10 text-app-accent hover:bg-indigo-500/20 hover:border-indigo-500/60'
          : 'border-emerald-500/40 bg-emerald-500/10 text-app-success hover:bg-emerald-500/20 hover:border-emerald-500/60'
      }`}
    >
      {busy ? (
        <span aria-hidden className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
      ) : isTextbook ? (
        <BookOpen className="h-3.5 w-3.5" aria-hidden />
      ) : (
        <Pencil className="h-3.5 w-3.5" aria-hidden />
      )}
      {spec}
    </button>
  );
}