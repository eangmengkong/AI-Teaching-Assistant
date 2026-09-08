/**
 * Centralized API helpers.
 * Base URL can be overridden with NEXT_PUBLIC_API_URL (see .env.example).
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, '') || 'http://localhost:8000';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

const TOKEN_KEY = 'ai_ta_token';

export interface AuthSession {
  access_token: string;
  token_type: string;
  user: { id: number; email: string; full_name?: string | null; telegram_chat_id?: string | null };
}

function readSession(): AuthSession | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(TOKEN_KEY);
    return raw ? (JSON.parse(raw) as AuthSession) : null;
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  return readSession()?.access_token ?? null;
}

/** HTTP headers carrying the current bearer token (empty when not logged in). */
export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Perform a request and throw a readable ApiError when the response is not ok.
 * Automatically adds JSON content-type and the bearer token.
 */
export async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...authHeaders(),
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const message =
      typeof data.detail === 'string' ? data.detail : `Request failed with status ${res.status}`;
    throw new ApiError(message, res.status);
  }
  return res.json() as Promise<T>;
}

/**
 * Read-only fetch that resolves to null instead of throwing.
 * Used for the parallel dashboard load so one failing endpoint does not
 * take down the whole page.
 */
export async function safeGet<T = unknown>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders() });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

/**
 * Fetch a binary response (e.g. a generated study PDF) with the bearer token.
 * Throws ApiError on failure; returns the decoded Blob on success.
 */
export async function apiBlob(path: string, init?: RequestInit): Promise<Blob> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const message =
      typeof data.detail === 'string' ? data.detail : `Request failed with status ${res.status}`;
    throw new ApiError(message, res.status);
  }
  return res.blob();
}

/** Open a downloaded Blob (PDF) in a new browser tab, then clean up the URL. */
export function openBlobInNewTab(blob: Blob): void {
  const url = URL.createObjectURL(blob);
  window.open(url, '_blank');
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}