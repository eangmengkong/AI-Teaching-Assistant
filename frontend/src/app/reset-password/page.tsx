'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { GraduationCap, ShieldCheck } from 'lucide-react';

import Button from '../../components/Button';
import Field from '../../components/Field';
import { resetPassword } from '../../lib/auth';

function ResetPasswordCard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setToken(searchParams.get('token'));
  }, [searchParams]);

  const missingToken = !token;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError('The two passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      await resetPassword(token as string, password);
      // Session is saved by resetPassword — straight into the dashboard.
      router.replace('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
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
        {missingToken ? (
          <div className="text-center">
            <h1 className="text-xl font-extrabold tracking-tight text-app-text">Reset link missing</h1>
            <p className="mt-2 text-sm leading-relaxed text-app-muted">
              This page needs a valid reset token. Open the latest link from your Telegram bot,
              or request a new one.
            </p>
            <Link
              href="/forgot-password"
              className="mt-6 inline-block rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-600/20 transition hover:from-indigo-500 hover:to-violet-500"
            >
              Request a new link
            </Link>
          </div>
        ) : (
          <>
            <div className="text-center">
              <span
                aria-hidden
                className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-glow-accent"
              >
                <ShieldCheck className="h-5 w-5" />
              </span>
              <h1 className="mt-4 text-xl font-extrabold tracking-tight text-app-text">Choose a new password</h1>
              <p className="mt-2 text-sm text-app-muted">
                Pick something strong — at least 6 characters.
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
                label="New password"
                type="password"
                required
                minLength={6}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                hint="At least 6 characters"
              />
              <Field
                label="Confirm new password"
                type="password"
                required
                minLength={6}
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="••••••••"
              />
              <Button type="submit" size="full" variant="primary" loading={busy}>
                {busy ? 'Saving…' : 'Set new password'}
              </Button>
            </form>
          </>
        )}
      </div>

      <p className="mt-6 text-center text-sm text-app-muted">
        <Link
          href="/login"
          className="font-semibold text-indigo-600 transition hover:text-indigo-500 dark:text-indigo-400"
        >
          Back to sign in
        </Link>
      </p>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-app-bg px-4 py-10">
      <Suspense
        fallback={<div className="text-sm text-app-muted">Loading reset form…</div>}
      >
        <ResetPasswordCard />
      </Suspense>
    </div>
  );
}
