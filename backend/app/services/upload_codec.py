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


class StreamDecompressor:
    """Incrementally inflate a compressed upload without buffering it in RAM.

    Sniffs the first byte to pick the zlib (RFC 1950, what the browser's
    ``CompressionStream('deflate')`` produces) or raw-DEFLATE wrapper, then
    inflates chunk by chunk so a 100 MB upload never needs 100 MB of memory.
    """

    def __init__(self) -> None:
        self._obj: "zlib._Decompress | None" = None

    def feed(self, data: bytes) -> bytes:
        if not data:
            return b""
        if self._obj is None:
            # zlib-wrapped streams start with 0x78 (CMF byte).
            wbits = 15 if data[:1] == b"\x78" else -15
            self._obj = zlib.decompressobj(wbits)
        try:
            return self._obj.decompress(data)
        except zlib.error as exc:
            raise InvalidCompressedUpload(str(exc)) from exc

    def finish(self) -> bytes:
        if self._obj is None:
            return b""
        try:
            return self._obj.flush()
        except zlib.error as exc:
            raise InvalidCompressedUpload(str(exc)) from exc
