'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { Bot, GraduationCap, Send } from 'lucide-react';

import Button from '../../components/Button';
import Field from '../../components/Field';
import { requestPasswordReset } from '../../lib/auth';

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentMessage, setSentMessage] = useState<string | null>(null);
  const [notLinkedHint, setNotLinkedHint] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setNotLinkedHint(null);
    setBusy(true);
    try {
      const result = await requestPasswordReset(email.trim());
      if (result.sent === false && result.detail) {
        setNotLinkedHint(result.detail);
      } else {
        setSentMessage(result.message);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-app-bg px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-3">
          <span
            aria-hidden
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 shadow-glow-accent"
          >
            <GraduationCap className="h-5 w-5 text-white" />
          </span>
          <div className="leading-tight">
            <p className="text-sm font-bold text-app-text">AI Teaching Assistant</p>
            <p className="text-[11px] font-medium text-app-accent">1 Central AI Agent</p>
          </div>
        </div>

        <div className="rounded-2xl border border-app-border bg-app-surface p-6 shadow-card sm:p-8">
          {sentMessage ? (
            <div className="text-center">
              <span
                aria-hidden
                className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-glow-accent"
              >
                <Send className="h-5 w-5" />
              </span>
              <h1 className="mt-4 text-xl font-extrabold tracking-tight text-app-text">Check your Telegram</h1>
              <p className="mt-2 text-sm leading-relaxed text-app-muted">
                {sentMessage} Open the bot and tap <span className="font-semibold text-app-text">“Reset my password”</span> —
                the link works for 30 minutes and can be used once.
              </p>
              <Button className="mt-6" size="full" variant="secondary" onClick={() => router.push('/login')}>
                Back to sign in
              </Button>
            </div>
          ) : (
            <>
              <div className="text-center">
                <span
                  aria-hidden
                  className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-glow-accent"
                >
                  <LockIcon />
                </span>
                <h1 className="mt-4 text-xl font-extrabold tracking-tight text-app-text">Forgot your password?</h1>
                <p className="mt-2 text-sm leading-relaxed text-app-muted">
                  Enter the email on your account and we&apos;ll send a secure reset link to your
                  linked Telegram chat.
                </p>
              </div>

              {error && (
                <div
                  role="alert"
                  className="mt-5 flex items-start gap-2 rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-600 dark:text-rose-300"
                >
                  <span aria-hidden>⚠️</span>
                  <span>{error}</span>
                </div>
              )}

              <form onSubmit={handleSubmit} className="mt-6 space-y-4">
                <Field
                  label="Account email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                />
                <Button type="submit" size="full" variant="primary" loading={busy}>
                  {busy ? 'Sending…' : 'Send reset link via Telegram'}
                </Button>
              </form>

              {notLinkedHint && (
                <div
                  role="status"
                  className="mt-4 flex items-start gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-600 dark:text-amber-300"
                >
                  <span aria-hidden>📩</span>
                  <span>{notLinkedHint}</span>
                </div>
              )}

              <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-xs text-app-faint">
                <Bot className="h-3.5 w-3.5" aria-hidden />
                Never used the bot? Send /start to it first, then retry.
              </p>
            </>
          )}
        </div>

        <p className="mt-6 text-center text-sm text-app-muted">
          Remembered it?{' '}
          <Link
            href="/login"
            className="font-semibold text-indigo-600 transition hover:text-indigo-500 dark:text-indigo-400"
          >
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  );
}

function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5" aria-hidden>
      <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}
