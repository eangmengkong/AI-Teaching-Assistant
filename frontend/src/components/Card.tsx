import type { ReactNode } from 'react';

const TINTS = {
  indigo: 'from-indigo-500 to-violet-500 text-white',
  emerald: 'from-emerald-500 to-teal-500 text-white',
  amber: 'from-amber-500 to-orange-500 text-white',
  violet: 'from-violet-500 to-fuchsia-500 text-white',
  slate: 'from-slate-500 to-slate-600 text-white',
} as const;

interface CardProps {
  id?: string;
  title?: string;
  subtitle?: string;
  /** Header icon — lucide SVG components get a gradient chip, emojis a soft chip. */
  icon?: ReactNode;
  /** Gradient used for the icon chip when it is an SVG. */
  tint?: keyof typeof TINTS;
  /** Optional element rendered on the right side of the header. */
  actions?: ReactNode;
  /** Lift the card slightly on hover (great for clickable surfaces). */
  hover?: boolean;
  children: ReactNode;
  className?: string;
}

function chipClassName(child: ReactNode, tint: keyof typeof TINTS): string {
  // Plain strings (emojis) get a soft square; everything else gets a gradient chip.
  const isEmoji = typeof child === 'string';
  const chip = isEmoji
    ? 'bg-app-hover/70 text-base'
    : `bg-gradient-to-br shadow-glow-accent ${TINTS[tint]}`;
  return `flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${chip}`;
}

/**
 * Consistent panel used across the dashboard: card background, rounded
 * corners, optional header (icon + title + subtitle) and right-aligned actions.
 */
export default function Card({
  id,
  title,
  subtitle,
  icon,
  tint = 'indigo',
  actions,
  hover = false,
  children,
  className = '',
}: CardProps) {
  const hasHeader = Boolean(title || actions);

  return (
    <div
      id={id}
      className={`rounded-2xl border border-app-border bg-app-surface p-6 shadow-card transition ${
        hover ? 'hover:-translate-y-0.5 hover:shadow-lifted hover:border-app-border-strong' : ''
      } ${className}`}
    >
      {hasHeader && (
        <div className="mb-5 flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            {icon && <span className={chipClassName(icon, tint)} aria-hidden>{icon}</span>}
            <div>
              {title && <h2 className="text-base font-bold leading-tight text-app-text">{title}</h2>}
              {subtitle && <p className="mt-0.5 text-xs leading-snug text-app-muted">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}