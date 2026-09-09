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

/* ------------------------------------------------------------------ */
/* Faster file upload support (free, zero npm packages)                */
/* ------------------------------------------------------------------ */

export interface UploadProgress {
  loaded: number;
  total: number;
}

type CompressionStreamCtor = new (encoding: string) => {
  readable: ReadableStream<Uint8Array>;
  writable: WritableStream<Uint8Array>;
};

/** Extensions that benefit from client-side DEFLATE before upload. */
const COMPRESSIBLE_EXTENSIONS = new Set(['.pdf', '.txt']);

/**
 * Compress the file with the browser's free built-in `CompressionStream`
 * before uploading it. This is 100% free (no service, no npm package) and
 * shrinks the payload, so big PDFs/TXT uploads take less wall-clock time.
 *
 * Gracefully skips compression when: the browser lacks the API, the file is
 * not text-like (DOCX/DOC are already ZIP), the file is tiny, or compression
 * would not help. The server accepts both compressed and plain uploads.
 */
export async function compressFileIfSupported(
  file: File,
): Promise<{ blob: Blob; compressed: boolean }> {
  const ext = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
  if (!COMPRESSIBLE_EXTENSIONS.has(ext)) return { blob: file, compressed: false };
  if (file.size < 256 * 1024) return { blob: file, compressed: false };

  const CompressionStream = (
    globalThis as unknown as { CompressionStream?: CompressionStreamCtor }
  ).CompressionStream;
  if (typeof CompressionStream !== 'function') return { blob: file, compressed: false };

  const bodyStream = new Response(file).body as ReadableStream<Uint8Array> | null;
  if (!bodyStream || typeof bodyStream.pipeThrough !== 'function') {
    return { blob: file, compressed: false };
  }

  try {
    const compressor = new CompressionStream('deflate');
    const compressedBody = bodyStream.pipeThrough(compressor);
    const blob = await new Response(compressedBody).blob();
    if (!blob || blob.size >= file.size) return { blob: file, compressed: false };
    return { blob, compressed: true };
  } catch {
    return { blob: file, compressed: false };
  }
}

/**
 * POST a multipart FormData body with real upload progress.
 *
 * Uses XMLHttpRequest `upload.onprogress` (free & built-in) so the UI can show
 * actual bytes transferred / MB per second instead of a fake timer.
 */
export async function apiUploadJson(
  path: string,
  form: FormData,
  onProgress?: (e: UploadProgress) => void,
): Promise<unknown> {
  const xhr = new XMLHttpRequest();
  xhr.open('POST', endpointUrl(path));

  const headers = authHeaders();
  Object.entries(headers).forEach(([key, value]) => xhr.setRequestHeader(key, value));

  const timeoutId = setTimeout(() => xhr.abort(), 30 * 60 * 1000);

  const promise = new Promise<unknown>((resolve, reject) => {
    if (xhr.upload) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress({ loaded: e.loaded, total: e.total });
      };
    }

    xhr.onload = () => {
      clearTimeout(timeoutId);
      let data: unknown = {};
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        // non-JSON error body — fall through to the status-based message
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data);
        return;
      }
      const detail = (data as { detail?: unknown }).detail;
      const message =
        typeof detail === 'string' ? detail : `Request failed with status ${xhr.status}`;
      reject(new ApiError(message, xhr.status));
    };

    xhr.onerror = () => {
      clearTimeout(timeoutId);
      reject(
        new ApiError(
          'The upload did not reach the server (network or browser-extension issue). ' +
            'Try a private window (extensions are disabled there) or a more stable connection.',
          0,
        ),
      );
    };
  });

  xhr.send(form);
  return promise;
}

/* ------------------------------------------------------------------ */
/* Chunked upload for large files (free, zero npm packages)            */
/* ------------------------------------------------------------------ */

/** Files larger than this are sent in parts — a whole 100 MB body in one
 * request OOM-kills small (512 MB RAM) hosting instances. */
export const CHUNKED_UPLOAD_THRESHOLD = 24 * 1024 * 1024;
const UPLOAD_CHUNK_SIZE = 4 * 1024 * 1024;

/**
 * Upload a large blob in ~4 MB parts. Each request is tiny, so neither the
 * network proxy nor the server needs to buffer the whole file; the server
 * assembles the parts inside Postgres. Progress is aggregated across parts.
 */
export async function apiUploadFileChunked(
  blob: Blob,
  filename: string,
  meta: { course_id: number; document_type: string; compressed: boolean },
  onProgress?: (e: UploadProgress) => void,
): Promise<unknown> {
  const totalChunks = Math.max(1, Math.ceil(blob.size / UPLOAD_CHUNK_SIZE));

  const init = await api<{ document_id: number; chunk_size: number }>(
    '/api/v1/documents/upload/init',
    {
      method: 'POST',
      body: JSON.stringify({
        course_id: meta.course_id,
        document_type: meta.document_type,
        filename,
        mime_type: blob.type || undefined,
        size: blob.size,
        total_chunks: totalChunks,
      }),
    },
  );

  const sendChunk = (seq: number, part: Blob, baseLoaded: number) =>
    new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', endpointUrl(`/api/v1/documents/upload/${init.document_id}/chunk`));
      Object.entries(authHeaders()).forEach(([k, v]) => xhr.setRequestHeader(k, v));
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve();
          return;
        }
        let detail: unknown;
        try {
          detail = JSON.parse(xhr.responseText)?.detail;
        } catch {
          /* non-JSON error body */
        }
        reject(
          new ApiError(
            typeof detail === 'string' ? detail : `Chunk upload failed with status ${xhr.status}`,
            xhr.status,
          ),
        );
      };
      xhr.onerror = () =>
        reject(
          new ApiError(
            'A part of the upload did not reach the server (network or browser-extension issue). ' +
              'Try a private window or a more stable connection.',
            0,
          ),
        );
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress({ loaded: baseLoaded + e.loaded, total: blob.size });
        }
      };
      const form = new FormData();
      form.append('seq', String(seq));
      form.append('chunk', part, `part-${seq}`);
      xhr.send(form);
    });

  for (let seq = 0; seq < totalChunks; seq += 1) {
    const start = seq * UPLOAD_CHUNK_SIZE;
    const part = blob.slice(start, Math.min(blob.size, start + UPLOAD_CHUNK_SIZE));
    // Retry each part (idempotent on the server) before giving up.
    let lastError: unknown = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        await sendChunk(seq, part, start);
        lastError = null;
        break;
      } catch (err) {
        lastError = err;
        if (err instanceof ApiError && err.status >= 400 && err.status < 500 && err.status !== 429) {
          break; // permanent client error — retrying will not help
        }
        await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
      }
    }
    if (lastError) throw lastError;
  }

  return api(`/api/v1/documents/upload/${init.document_id}/complete`, {
    method: 'POST',
    body: JSON.stringify({ size: blob.size, total_chunks: totalChunks }),
  });
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