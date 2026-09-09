/**
 * Centralized API helpers.
 * Base URL can be overridden with NEXT_PUBLIC_API_URL (see .env.example).
 * It may be given with or without the /api/v1 prefix — it is normalized here
 * so every request targets exactly one /api/v1 in every environment.
 */

const API_ROOT =
  (process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, '') || 'http://localhost:8000').replace(
    /\/api\/v1$/,
    '',
  );

/** API root that always ends with /api/v1, e.g. https://host/api/v1 */
export const API_BASE = `${API_ROOT}/api/v1`;

/**
 * Build a fetch URL from a path. Accepts both "/api/v1/lessons" (the
 * convention used across the app) and "/lessons", and never duplicates the
 * /api/v1 prefix regardless of how NEXT_PUBLIC_API_URL is configured.
 */
function endpointUrl(path: string): string {
  return `${API_BASE}${path.replace(/^\/api\/v1(?=\/|$)/, '')}`;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/**
 * Wrap fetch so that network-level failures (DNS, TLS, connection reset or a
 * browser extension killing the request) surface as a readable ApiError
 * instead of a bare TypeError:"Failed to fetch". This keeps the UI able to
 * show what went wrong — without this, an ad-blocker/security extension
 * dropping a large upload would appear as a generic console error with no
 * explanation in the page.
 */
async function fetchOrThrow(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(endpointUrl(path), init);
  } catch (err) {
    if (err instanceof Error && (err.name === 'AbortError' || err.message.includes('abort'))) {
      throw new ApiError('Request timed out. If you were uploading, please try again on a stable connection.', 0);
    }
    // This is the network/extension failure path.
    throw new ApiError(
      'The request did not reach the server (network or browser-extension issue). ' +
        'If it keeps happening, try a private window (extensions are disabled there) or disable ad/security extensions.',
      0,
    );
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
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30 * 60 * 1000);

  const res = await fetchOrThrow(path, {
    ...init,
    signal: controller.signal,
    headers: {
      ...authHeaders(),
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers ?? {}),
    },
  });

  clearTimeout(timeoutId);

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
    const res = await fetchOrThrow(path, { headers: authHeaders() });
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
  const res = await fetchOrThrow(path, {
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