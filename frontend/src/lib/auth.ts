import { API_BASE, api, type AuthSession } from './api';

/**
 * Auth endpoints always live under /api/v1. NEXT_PUBLIC_API_URL may or may not
 * already include that prefix (production sets it WITH the prefix, localhost
 * without), so normalize it once here instead of hardcoding it in every URL.
 */
const API_V1 = API_BASE; // API_BASE is already normalized to end with /api/v1

const TOKEN_KEY = 'ai_ta_token';

export type { AuthSession };

export function getSession(): AuthSession | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(TOKEN_KEY);
    return raw ? (JSON.parse(raw) as AuthSession) : null;
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  return getSession()?.access_token ?? null;
}

export function saveSession(session: AuthSession): void {
  try {
    localStorage.setItem(TOKEN_KEY, JSON.stringify(session));
  } catch {
    // storage unavailable (private mode) — the user can still use the app
  }
}

export function clearSession(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

export function isLoggedIn(): boolean {
  return Boolean(getToken());
}

/** Exchange email/password for a bearer token via the OAuth2 form endpoint. */
export async function login(email: string, password: string): Promise<AuthSession> {
  const res = await fetch(`${API_V1}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: email, password }),
  });
  const data = (await res.json().catch(() => null)) as Partial<AuthSession> | null;
  if (!res.ok || !data?.access_token) {
    const detail = (data as { detail?: string } | null)?.detail;
    throw new Error(typeof detail === 'string' ? detail : 'Login failed. Check your credentials.');
  }
  saveSession(data as AuthSession);
  return data as AuthSession;
}

/** Register a new account, then automatically signs in. */
export async function register(input: {
  email: string;
  password: string;
  full_name?: string | null;
}): Promise<AuthSession> {
  const res = await fetch(`${API_V1}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  const data = (await res.json().catch(() => null)) as { detail?: string } | null;
  if (!res.ok || data?.detail) {
    throw new Error(data?.detail || 'Registration failed.');
  }
  return login(input.email, input.password);
}

export function logout(): void {
  clearSession();
}

export interface PasswordResetResult {
  message: string;
  sent?: boolean;
  detail?: string;
}

/** Ask the backend to send a password-reset link to the user's Telegram. */
export async function requestPasswordReset(email: string): Promise<PasswordResetResult> {
  const res = await fetch(`${API_V1}/auth/forgot-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  const data = (await res.json().catch(() => null)) as PasswordResetResult | null;
  if (!res.ok) throw new Error(data?.detail || 'Could not start the reset. Try again.');
  return data ?? { message: 'Reset link sent.' };
}

/** Exchange a reset token for a new password, then sign in with it. */
export async function resetPassword(token: string, newPassword: string): Promise<AuthSession> {
  const res = await fetch(`${API_V1}/auth/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  const data = (await res.json().catch(() => null)) as Partial<AuthSession> & { detail?: string } | null;
  if (!res.ok || !data?.access_token) {
    throw new Error(data?.detail || 'Reset failed. The link may have expired — request a new one.');
  }
  const session = data as AuthSession;
  saveSession(session);
  return session;
}

/** Change the password of the logged-in user (requires current password). */
export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await api<{ message: string }>('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}