'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { Bot, Lock, ShieldCheck } from 'lucide-react';

import Button from '../../../components/Button';
import Card from '../../../components/Card';
import Field from '../../../components/Field';
import PageHeader from '../../../components/PageHeader';
import { changePassword, getSession } from '../../../lib/auth';

export default function AccountSettingsPage() {
  const router = useRouter();
  const session = getSession();
  const email = session?.user.email ?? '';

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (newPassword !== confirm) {
      setError('The two new passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      await changePassword(currentPassword, newPassword);
      setSuccess('Password updated — use it the next time you sign in.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirm('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update the password.');
    } finally {
      setBusy(false);
    }
  };

  const telegramLinked = Boolean(session?.user.telegram_chat_id);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Account & Security"
        subtitle="Manage your password and how recovery links reach you."
        icon={<Lock className="h-6 w-6" />}
        tint="violet"
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <Card
          className="lg:col-span-3"
          title="Change password"
          subtitle="Requires your current password."
          icon={<ShieldCheck className="h-4 w-4" />}
          tint="indigo"
        >
          {success && (
            <div
              role="status"
              className="mb-4 flex items-start gap-2 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-600 dark:text-emerald-300"
            >
              <span aria-hidden>✅</span>
              <span>{success}</span>
            </div>
          )}
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
            <Field
              label="Current password"
              type="password"
              required
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="••••••••"
            />
            <Field
              label="New password"
              type="password"
              required
              minLength={6}
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
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
            <Button type="submit" variant="primary" loading={busy}>
              {busy ? 'Updating…' : 'Update password'}
            </Button>
          </form>
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <Card title="Account" icon="👤" tint="slate">
            <dl className="space-y-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-app-muted">Email</dt>
                <dd className="truncate font-semibold text-app-text">{email || '—'}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-app-muted">Name</dt>
                <dd className="truncate font-semibold text-app-text">
                  {session?.user.full_name?.trim() || '—'}
                </dd>
              </div>
            </dl>
          </Card>

          <Card
            title="Password recovery"
            subtitle="Where reset links are sent if you forget your password."
            icon={<Bot className="h-4 w-4" />}
            tint="emerald"
          >
            <div
              className={`flex items-start gap-2 rounded-xl border px-3 py-2.5 text-sm ${
                telegramLinked
                  ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300'
                  : 'border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-300'
              }`}
            >
              <span aria-hidden>{telegramLinked ? '✅' : '⚠️'}</span>
              <span>
                {telegramLinked
                  ? 'Telegram is linked — reset links arrive instantly from your bot.'
                  : 'No Telegram chat linked yet. Send /start to your bot, then reload this page.'}
              </span>
            </div>
            <Button className="mt-4" size="sm" variant="secondary" onClick={() => router.push('/forgot-password')}>
              Preview reset flow
            </Button>
          </Card>
        </div>
      </div>
    </div>
  );
}
