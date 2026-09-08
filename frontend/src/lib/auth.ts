import { API_BASE, type AuthSession } from './api';

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
  const res = await fetch(`${API_BASE}/api/v1/auth/token`, {
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
  const res = await fetch(`${API_BASE}/api/v1/auth/register`, {
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