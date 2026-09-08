'use client';

import { useId } from 'react';
import type { InputHTMLAttributes } from 'react';

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
}

/**
 * Labelled input with consistent theme styling, focus ring and optional hint.
 * The label is connected to the input via useId for accessibility.
 */
export default function Field({ label, hint, className = '', id, ...props }: FieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;

  return (
    <div className="min-w-0">
      <label htmlFor={inputId} className="mb-1.5 block text-xs font-semibold text-app-soft">
        {label}
      </label>
      <input
        id={inputId}
        className={`w-full rounded-xl border border-app-border bg-app-input px-3 py-2.5 text-sm text-app-text placeholder:text-app-faint transition focus:border-indigo-500/70 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:shadow-glow-field disabled:opacity-60 ${className}`}
        {...props}
      />
      {hint && <p className="mt-1 text-[11px] text-app-muted">{hint}</p>}
    </div>
  );
}