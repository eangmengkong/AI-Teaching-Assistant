"""Cloudflare R2 object storage for uploaded file bytes.

Why R2 instead of the database?
-------------------------------
Neon's Free plan only includes 5 GB of public network transfer per project per
month. Storing multi-MB textbook/workbook PDFs in Postgres
(``documents.file_data``) burns that quota in a handful of uploads — every file
crosses the wire several times (chunk uploads, the BYTEA concat, parsing,
page-PDF building, Telegram delivery). Cloudflare R2 offers **10 GB-month of
free storage and unlimited free egress**, and is S3-compatible, so we talk to
it with boto3.

Row layout
----------
``documents.file_path`` holds the remote object key with an ``r2://`` prefix
when the bytes live only in R2::

    r2://documents/{course_id}/{document_type}/{uuid4}{ext}

``documents.file_data`` stays NULL for those rows and remains supported as the
fallback for local development / environments without R2 configured.
"""

import os
import uuid
from typing import Optional

from app.core.config import settings

try:
    import boto3
except ImportError:  # pragma: no cover - optional, enables graceful fallback
    boto3 = None

REMOTE_PREFIX = "r2://"

# Lazy boto3 client cache (created on first use).
_client = None  # type: ignore


def r2_enabled() -> bool:
    """True when Cloudflare R2 is configured, so callers prefer R2 storage."""
    return bool(
        settings.R2_ACCOUNT_ID
        and settings.R2_ACCESS_KEY_ID
        and settings.R2_SECRET_ACCESS_KEY
        and settings.R2_BUCKET
    )


def _get_client():
    """Return the cached boto3 S3 client pointed at Cloudflare R2 (or None)."""
    global _client
    if not r2_enabled():
        return None
    if boto3 is None:
        raise RuntimeError(
            "Cloudflare R2 is configured but boto3 is not installed; "
            "run `pip install -r requirements.txt`."
        )
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        )
    return _client


def is_remote_path(value: Optional[str]) -> bool:
    """True when ``value`` is an ``r2://`` remote object path."""
    return bool(value and value.startswith(REMOTE_PREFIX))


def build_document_key(course_id: int, document_type: str, filename: str) -> str:
    """Unique object key under the ``documents/`` prefix (never collides)."""
    ext = os.path.splitext(filename or "")[1].lower() or ".bin"
    return (
        f"documents/{int(course_id)}/{document_type.strip().lower()}/"
        f"{uuid.uuid4().hex}{ext}"
    )


def store_document_file(
    course_id: int,
    document_type: str,
    filename: str,
    path: str,
    mime_type: str = "application/octet-stream",
) -> str:
    """Upload a file already on disk to R2 and return the remote path.

    Uses boto3's multipart ``upload_fileobj`` so large assembled uploads
    (hundreds of MB) stream from disk in small parts - the whole file is
    never held in RAM. This keeps the DB free of giant BYTEA rows on
    free-tier Postgres nodes that choke on them.
    """
    client = _get_client()
    if client is None:
        raise RuntimeError("Cloudflare R2 is not configured; falling back to DB storage.")
    key = build_document_key(course_id, document_type, filename)
    with open(path, "rb") as fh:
        client.upload_fileobj(
            fh,
            Bucket=settings.R2_BUCKET,
            Key=key,
            ExtraArgs={"ContentType": mime_type or "application/octet-stream"},
        )
    return f"{REMOTE_PREFIX}{key}"


def store_document_bytes(
    course_id: int,
    document_type: str,
    filename: str,
    data: bytes,
    mime_type: str = "application/octet-stream",
) -> str:
    """Upload ``data`` to R2 and return the remote path (``r2://<key>``).

    Raises RuntimeError when R2 is not usable, so callers can fall back to
    database storage instead of losing the upload.
    """
    if not data:
        raise ValueError("Cannot store empty document bytes.")
    client = _get_client()
    if client is None:
        raise RuntimeError("Cloudflare R2 is not configured; falling back to DB storage.")
    key = build_document_key(course_id, document_type, filename)
    client.put_object(
        Bucket=settings.R2_BUCKET,
        Key=key,
        Body=data,
        ContentType=mime_type or "application/octet-stream",
    )
    return f"{REMOTE_PREFIX}{key}"


def delete_document_path(remote_path: str) -> None:
    """Best-effort removal of an ``r2://`` object (missing objects are ignored)."""
    if not is_remote_path(remote_path):
        return
    client = _get_client()
    if client is None:
        return
    try:
        client.delete_object(
            Bucket=settings.R2_BUCKET,
            Key=remote_path[len(REMOTE_PREFIX):],
        )
    except Exception:
        pass


def load_document_bytes(doc) -> Optional[bytes]:
    """Return a document's raw file bytes from wherever they live.

    Resolution order:
      1. R2 object (``doc.file_path`` starts with ``r2://``)
      2. local file on disk (``doc.file_path`` is an existing path)
      3. ``doc.file_data`` (legacy DB storage)

    Returns None when the bytes are not available anywhere.
    """
    if is_remote_path(doc.file_path):
        client = _get_client()
        if client is None:
            return None
        try:
            resp = client.get_object(
                Bucket=settings.R2_BUCKET,
                Key=doc.file_path[len(REMOTE_PREFIX):],
            )
            return resp["Body"].read()
        except Exception:
            return None
    if doc.file_path and os.path.exists(doc.file_path):
        try:
            with open(doc.file_path, "rb") as fh:
                return fh.read()
        except OSError:
            return None
    return doc.file_data or None


def has_document_bytes(doc) -> bool:
    """Cheap presence check (no download) used by the background worker."""
    if is_remote_path(doc.file_path):
        return True
    if doc.file_path and os.path.exists(doc.file_path):
        return True
    return bool(doc.file_data)