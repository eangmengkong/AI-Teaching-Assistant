import type { ReactNode } from 'react';

const TINTS = {
  indigo: 'from-indigo-500 to-violet-500 text-white',
  emerald: 'from-emerald-500 to-teal-500 text-white',
  violet: 'from-violet-500 to-fuchsia-500 text-white',
  amber: 'from-amber-500 to-orange-500 text-white',
  slate: 'from-slate-500 to-slate-600 text-white',
} as const;

interface PageHeaderProps {
  title: string;
  subtitle: string;
  /** lucide icon element, e.g. <GraduationCap className="h-6 w-6" /> */
  icon?: ReactNode;
  tint?: keyof typeof TINTS;
  /** Right-aligned action buttons / links. */
  actions?: ReactNode;
  /** Small meta chips rendered under the header, e.g. "12 Sessions". */
  meta?: ReactNode;
}

/**
 * Consistent page heading used at the top of every dashboard route:
 * gradient icon chip + title/subtitle on the left, actions on the right.
 */
export default function PageHeader({ title, subtitle, icon, tint = 'indigo', actions, meta }: PageHeaderProps) {
  return (
    <header className="animate-fade-up">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          {icon && (
            <span
              aria-hidden
              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br shadow-glow-accent ${TINTS[tint]}`}
            >
              {icon}
            </span>
          )}
          <div className="min-w-0">
            <h1 className="text-2xl font-extrabold tracking-tight text-app-text sm:text-3xl">{title}</h1>
            <p className="mt-1 text-sm leading-snug text-app-muted">{subtitle}</p>
          </div>
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {meta && <div className="mt-3 flex flex-wrap items-center gap-2">{meta}</div>}
    </header>
  );
}