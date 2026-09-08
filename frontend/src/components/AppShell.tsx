'use client';

import {
  Bot,
  CalendarDays,
  FileText,
  GraduationCap,
  LayoutDashboard,
  Lock,
  LogOut,
  Menu,
  Settings,
  TrendingUp,
  X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { useState } from 'react';

import ThemeToggle from './ThemeToggle';
import { getSession, logout } from '../lib/auth';

interface NavItem {
  href: string;
  id: string;
  label: string;
  icon: LucideIcon;
}

const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: 'Workspace',
    items: [
      { href: '/', id: 'overview', label: 'Overview', icon: LayoutDashboard },
      { href: '/setup', id: 'setup', label: 'Course Setup', icon: Settings },
      { href: '/documents', id: 'documents', label: 'Documents', icon: FileText },
    ],
  },
  {
    title: 'Planning',
    items: [
      { href: '/schedule', id: 'schedule', label: '1-Month Schedule', icon: CalendarDays },
      { href: '/progress', id: 'progress', label: 'Progress & Scores', icon: TrendingUp },
    ],
  },
  {
    title: 'Account',
    items: [
      { href: '/settings', id: 'settings', label: 'Account & Security', icon: Lock },
    ],
  },
];

/**
 * Responsive app shell shared by every dashboard route: fixed sidebar on
 * desktop, collapsible drawer + sticky top bar on tablet/mobile. Active nav
 * state is derived from the current path so the sidebar works across pages.
 */
export default function AppShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const pathname = usePathname();

  const session = getSession();
  const displayName = session?.user.full_name?.trim() || session?.user.email || 'Teacher';
  const initials = displayName
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');

  const handleLogout = () => {
    logout();
    window.location.replace('/login');
  };

  const isActive = (href: string) => (href === '/' ? pathname === '/' : pathname === href);

  const renderBrand = (compact = false) => (
    <div className={`flex items-center gap-3 ${compact ? '' : 'px-2'}`}>
      <span
        aria-hidden
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 animate-gradient shadow-glow-accent"
      >
        <GraduationCap className="h-5 w-5 text-white" />
      </span>
      <div className="min-w-0 leading-tight">
        <p className="truncate text-sm font-bold text-app-text">AI Teaching Assistant</p>
        <p className="text-[11px] font-medium text-app-accent">1 Central AI Agent</p>
      </div>
    </div>
  );
const renderNavItem = (item: NavItem, onNavigate: () => void) => {
    const active = isActive(item.href);
    const Icon = item.icon;
    return (
      <a
        key={item.id}
        href={item.href}
        aria-current={active ? 'page' : undefined}
        onClick={onNavigate}
        className={`relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70 ${
          active
            ? 'bg-gradient-to-r from-indigo-500/15 via-violet-500/10 to-transparent text-app-accent shadow-sm'
            : 'text-app-muted hover:bg-app-hover/70 hover:text-app-soft'
        }`}
      >
        <span
          aria-hidden
          className={`absolute inset-y-1 left-0 w-[3px] rounded-full ${
            active ? 'bg-gradient-to-b from-indigo-500 to-violet-500 opacity-100' : 'bg-transparent opacity-0'
          } transition-opacity`}
        />
        <span
          aria-hidden
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
            active ? 'bg-indigo-500/15' : 'bg-app-surface-2/70'
          }`}
        >
          <Icon className={`h-4.5 w-4.5 ${active ? 'text-app-accent' : 'text-app-muted'}`} />
        </span>
        <span className="truncate">{item.label}</span>
      </a>
    );
  };

  const renderNav = (onNavigate: () => void) => (
    <nav aria-label="Main navigation" className="space-y-5">
      {NAV_GROUPS.map((group) => (
        <div key={group.title}>
          <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-widest text-app-faint">{group.title}</p>
          <div className="space-y-0.5">{group.items.map((item) => renderNavItem(item, onNavigate))}</div>
        </div>
      ))}
    </nav>
  );

  const renderUserCard = () => (
    <div className="flex items-center gap-3 rounded-xl border border-app-border bg-app-surface-2 p-2.5">
      <span
        aria-hidden
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-xs font-bold text-white"
      >
        {initials}
      </span>
      <div className="min-w-0 flex-1 leading-tight">
        <p className="truncate text-xs font-bold text-app-text">{displayName}</p>
        <p className="text-[10px] text-app-muted">{session?.user.email ?? 'teacher account'}</p>
      </div>
      <ThemeToggle compact />
    </div>
  );
const renderServerStatus = () => (
    <div className="rounded-xl border border-app-border bg-app-surface-2/60 p-3 text-xs text-app-muted">
      <div className="mb-1 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse-soft" aria-hidden />
        <span className="font-semibold text-app-soft">Server Scheduler</span>
      </div>
      <p className="flex items-center gap-1.5">
        <Bot className="h-3.5 w-3.5 text-app-accent" aria-hidden />
        Telegram &amp; Calendar sync active.
      </p>
    </div>
  );

  const renderAccountFooter = () => (
    <button
      type="button"
      onClick={handleLogout}
      className="inline-flex w-full items-center gap-2 rounded-xl border border-app-border bg-app-surface-2 px-3 py-2 text-xs font-semibold text-app-muted transition hover:border-rose-500/40 hover:bg-rose-500/10 hover:text-rose-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70"
    >
      <LogOut className="h-4 w-4" aria-hidden />
      Logout
    </button>
  );

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-72 shrink-0 flex-col border-r border-app-border bg-app-surface lg:flex">
        <div className="flex h-[72px] items-center border-b border-app-border px-6">{renderBrand()}</div>
        <div className="flex-1 overflow-y-auto p-4">{renderNav(() => {})}</div>
        <div className="space-y-2.5 p-4">
          {renderServerStatus()}
          {renderUserCard()}
          {renderAccountFooter()}
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        {/* Mobile top bar */}
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-app-border bg-app-surface/90 px-4 backdrop-blur lg:hidden">
          {renderBrand(true)}
          <div className="flex items-center gap-1">
            <ThemeToggle compact />
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label="Open navigation"
              className="inline-flex h-10 w-10 items-center justify-center rounded-xl text-app-muted transition hover:bg-app-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70"
            >
              <Menu className="h-5 w-5" aria-hidden />
            </button>
          </div>
        </header>
{/* Mobile drawer */}
        {menuOpen && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setMenuOpen(false)} aria-hidden />
            <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-app-surface shadow-2xl">
              <div className="flex h-16 items-center justify-between border-b border-app-border px-4">
                {renderBrand(true)}
                <button
                  type="button"
                  onClick={() => setMenuOpen(false)}
                  aria-label="Close navigation"
                  className="inline-flex h-10 w-10 items-center justify-center rounded-xl text-app-muted transition hover:bg-app-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70"
                >
                  <X className="h-5 w-5" aria-hidden />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4">{renderNav(() => setMenuOpen(false))}</div>
              <div className="space-y-2.5 p-4">
                {renderServerStatus()}
                {renderUserCard()}
                {renderAccountFooter()}
              </div>
            </aside>
          </div>
        )}

        {/* Main content */}
        <main className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-10 lg:py-8">{children}</main>
      </div>
    </div>
  );
}