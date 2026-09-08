'use client';

import { Moon } from 'lucide-react';
import { Sun } from 'lucide-react';
import { useEffect, useState } from 'react';

/**
 * Light/dark toggle. Persists the choice in localStorage and flips the
 * `dark` class on <html>; globals.css maps that class to a matching palette.
 */
export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const [dark, setDark] = useState(true);

  useEffect(() => {
    setDark(document.documentElement.classList.contains('dark'));
  }, []);

  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle('dark', next);
    try {
      localStorage.setItem('theme', next ? 'dark' : 'light');
    } catch {
      // ignore
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      title={dark ? 'Light mode' : 'Dark mode'}
      className={`inline-flex items-center justify-center rounded-xl border border-app-border bg-app-surface-2 text-app-muted transition hover:text-app-soft focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70 ${
        compact ? 'h-9 w-9' : 'h-9 w-9'
      }`}
    >
      {dark ? <Sun className="h-4.5 w-4.5" aria-hidden /> : <Moon className="h-4.5 w-4.5" aria-hidden />}
    </button>
  );
}