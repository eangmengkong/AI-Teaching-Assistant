'use client';

import type { ToastData } from '../lib/useToast';

const CONFIG = {
  success: { icon: '✓', className: 'border-emerald-500/40 bg-emerald-950/95 text-app-success' },
  error: { icon: '✕', className: 'border-rose-500/40 bg-rose-950/95 text-rose-400' },
  info: { icon: 'i', className: 'border-indigo-500/40 bg-indigo-950/95 text-app-accent' },
} as const;

/** Accessible toast rendered in the bottom-right; auto-dismisses via useToast. */
export default function Toast({ toast }: { toast: ToastData | null }) {
  if (!toast) return null;
  const { icon, className } = CONFIG[toast.type];

  return (
    <div role="status" aria-live="polite" className="toast-in fixed bottom-4 right-4 z-50 sm:bottom-6 sm:right-6">
      <div className={`flex max-w-xs items-center gap-3 rounded-2xl border px-4 py-3 text-sm text-app-text shadow-2xl backdrop-blur ${className}`}>
        <span aria-hidden className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-current/15 text-xs font-black`}>
          {icon}
        </span>
        <span className="font-medium">{toast.message}</span>
      </div>
    </div>
  );
}