'use client';

import { Bot, CalendarCheck, GraduationCap, Library, Sparkles, Zap } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import type { FormEvent } from 'react';

import Button from '../../components/Button';
import Field from '../../components/Field';
import ThemeToggle from '../../components/ThemeToggle';
import { login, register } from '../../lib/auth';

type Mode = 'login' | 'register';

const FEATURES = [
  { icon: CalendarCheck, text: '1-month schedule built & pushed to Google Calendar' },
  { icon: Library, text: 'Textbook & workbook page references in every lesson' },
  { icon: Bot, text: 'Study PDFs delivered straight to Telegram' },
  { icon: Zap, text: 'One central AI agent — no more juggling tools' },
];

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === 'login') {
        await login(email.trim(), password);
      } else {
        await register({ email: email.trim(), password, full_name: fullName.trim() || null });
      }
      router.replace('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
  };

  return (
    <div className="flex min-h-screen flex-col bg-app-bg lg:flex-row">
      {/* Brand panel */}
      <div className="relative flex flex-1 items-center justify-center overflow-hidden border-b border-app-border bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-600 px-6 py-10 animate-gradient lg:border-r">
        <div className="absolute inset-0 bg-grid opacity-60" aria-hidden />
        <div aria-hidden className="absolute -left-16 -top-16 h-72 w-72 rounded-full bg-white/10 blur-2xl animate-float" />
        <div
          aria-hidden
          className="absolute -bottom-24 -right-10 h-80 w-80 rounded-full bg-fuchsia-300/15 blur-3xl animate-float"
          style={{ animationDelay: '1.6s' }}
        />

        <div className="relative w-full max-w-md text-white">
          <div className="flex items-center gap-3">
            <span aria-hidden className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-white/15 backdrop-blur">
              <GraduationCap className="h-6 w-6" />
            </span>
            <div className="leading-tight">
              <p className="text-sm font-bold">AI Teaching Assistant</p>
              <p className="text-xs text-indigo-100">1 Central AI Agent</p>
            </div>
          </div>

          <h1 className="mt-8 text-3xl font-extrabold tracking-tight sm:text-4xl">
            Teach one month.
            <br />
            <span className="text-brand-gradient">Let the agent run the rest.</span>
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-indigo-100/90">
            Upload your materials once — the AI plans every session, references the exact
            pages and keeps your calendar, chat and scores in perfect sync.
          </p>

          <ul className="mt-8 space-y-3">
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <li key={f.text} className="flex items-start gap-3 text-sm">
                  <span aria-hidden className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white/15">
                    <Icon className="h-4.5 w-4.5" />
                  </span>
                  <span className="leading-snug">{f.text}</span>
                </li>
              );
            })}
          </ul>

          <div className="mt-8 inline-flex items-center gap-2 rounded-2xl border border-white/20 bg-white/10 px-4 py-2.5 text-xs text-indigo-100 backdrop-blur">
            <span className="h-2 w-2 rounded-full bg-emerald-300 animate-pulse-soft" aria-hidden />
            Server scheduler · Telegram &amp; Google Calendar sync active
          </div>
        </div>
      </div>
      <div className="flex flex-1 flex-col items-center justify-center px-4 py-8">
        <div className="w-full max-w-md rounded-2xl border border-app-border bg-app-surface p-6 shadow-lifted sm:p-8">
          <div className="mb-6 flex flex-col items-center">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-500/20 bg-indigo-500/5 px-3 py-1 text-[11px] font-semibold text-app-accent">
              <Sparkles className="h-3.5 w-3.5" aria-hidden />
              Central AI Teaching Agent
            </span>
            <h2 className="mt-3 text-xl font-extrabold tracking-tight text-app-text">
              {mode === 'login' ? 'Welcome back' : 'Create your account'}
            </h2>
            <p className="mt-1 text-sm text-app-muted">
              {mode === 'login' ? 'Sign in to open your dashboard' : 'Set up your teaching workspace'}
            </p>
          </div>

          {/* Mode toggle */}
          <div className="mb-6 grid grid-cols-2 gap-1 rounded-xl border border-app-border bg-app-surface-2 p-1" role="tablist" aria-label="Authentication mode">
            {(['login', 'register'] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={mode === m}
                onClick={() => switchMode(m)}
                className={`rounded-lg px-3 py-2 text-sm font-semibold capitalize transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70 ${
                  mode === m ? 'bg-app-surface text-app-text shadow-sm' : 'text-app-muted hover:text-app-soft'
                }`}
              >
                {m}
              </button>
            ))}
          </div>

          {error && (
            <div
              role="alert"
              className="mb-4 flex items-start gap-2 rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-600 dark:text-rose-300"
            >
              <span aria-hidden>⚠️</span>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'register' && (
              <Field
                label="Full name"
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Your name (optional)"
              />
            )}
            <Field
              label="Email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
            <Field
              label="Password"
              type="password"
              required
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              hint={mode === 'register' ? 'At least 6 characters' : undefined}
            />

            <Button type="submit" size="full" loading={busy} variant="primary">
              {busy ? 'Please wait…' : mode === 'login' ? 'Sign In' : 'Create Account'}
            </Button>
          </form>

          <p className="mt-6 text-center text-[11px] leading-relaxed text-app-faint">
            After running the SQLite → Neon migration, the demo account is
            <br />
            <span className="font-mono text-app-muted">teacher@local.com / admin123</span>
          </p>
        </div>

        <div className="mt-5 inline-flex items-center gap-2 rounded-full border border-app-border bg-app-surface-2 px-3 py-1.5 text-xs text-app-muted">
          <ThemeToggle compact />
          Toggle theme
        </div>
      </div>
    </div>
  );
}