'use client';

import type { ButtonHTMLAttributes } from 'react';

type Variant = 'primary' | 'success' | 'warning' | 'danger' | 'secondary' | 'ghost';
type Size = 'sm' | 'md' | 'lg' | 'full';

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: 'bg-gradient-to-br from-indigo-600 to-violet-600 text-white hover:from-indigo-500 hover:to-violet-500 shadow-lg shadow-indigo-600/20',
  success: 'bg-gradient-to-br from-emerald-600 to-teal-600 text-white hover:from-emerald-500 hover:to-teal-500 shadow-lg shadow-emerald-600/20',
  warning: 'bg-gradient-to-br from-amber-500 to-orange-500 text-white hover:from-amber-400 hover:to-orange-400 shadow-lg shadow-amber-500/20',
  danger: 'bg-gradient-to-br from-rose-600 to-red-600 text-white hover:from-rose-500 hover:to-red-500 shadow-lg shadow-rose-600/20',
  secondary: 'border border-app-border bg-app-surface-2 text-app-soft hover:bg-app-hover hover:text-app-text',
  ghost: 'border border-app-border bg-transparent text-app-subtle hover:bg-app-hover hover:text-app-soft',
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
  lg: 'px-5 py-2.5 text-sm',
  full: 'w-full py-3 text-sm',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** Shows a small spinner and disables the button. */
  loading?: boolean;
}

export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  className = '',
  children,
  type = 'button',
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={`inline-flex select-none items-center justify-center gap-2 rounded-xl font-semibold shadow-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-app-bg active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
      {...props}
    >
      {loading && (
        <span aria-hidden className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}