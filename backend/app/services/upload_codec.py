"""Encoding helpers for faster uploads.

The dashboard compresses text-like files (PDF/TXT) with the browser's free
built-in ``CompressionStream`` before sending them. This module decodes that
payload back to the original bytes on the server, accepting both the RFC-1950
zlib wrapper and raw DEFLATE so any browser implementation works.
"""

import zlib


class InvalidCompressedUpload(Exception):
    """Raised when a payload marked ``compressed`` is not valid DEFLATE data."""


def decompress_payload(raw: bytes, compressed: bool) -> bytes:
    """Return the original bytes for a (possibly compressed) upload body."""
    if not compressed:
        return raw
    try:
        return zlib.decompress(raw)  # zlib wrapper (RFC 1950)
    except zlib.error:
        try:
            return zlib.decompress(raw, -15)  # raw DEFLATE fallback
        except zlib.error as exc:
            raise InvalidCompressedUpload(str(exc)) from exc