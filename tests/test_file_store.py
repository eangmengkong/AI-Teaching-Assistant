"""Unit tests for the Cloudflare R2 file store (no network / no boto3 needed)."""

import io
from types import SimpleNamespace

import pytest

from app.services import file_store


class FakeR2Client:
    """In-memory stand-in for the boto3 S3 client (put/get/delete only)."""

    def __init__(self):
        self.objects = {}

    def put_object(self, *, Bucket, Key, Body, ContentType=None):
        self.objects[Key] = bytes(Body)

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.objects[Key])}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop(Key, None)


@pytest.fixture
def r2(monkeypatch):
    """Make the store think R2 is configured and use the fake client."""
    fake = FakeR2Client()
    for attr in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.setattr(file_store.settings, attr, f"test-{attr}")
    monkeypatch.setattr(file_store, "_get_client", lambda: fake)
    monkeypatch.setattr(file_store, "_client", None)
    return fake


def _doc(**kwargs):
    defaults = dict(file_path="", file_data=None)
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_r2_disabled_without_config(monkeypatch):
    for attr in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.setattr(file_store.settings, attr, "")
    assert file_store.r2_enabled() is False


def test_key_and_remote_path_detection():
    key = file_store.build_document_key(3, "Textbook", "My Book.PDF")
    assert key.startswith("documents/3/textbook/")
    assert key.endswith(".pdf")
    assert "/" in key

    assert file_store.is_remote_path(f"r2://{key}") is True
    assert file_store.is_remote_path("") is False
    assert file_store.is_remote_path(None) is False


def test_store_and_load_roundtrip(r2):
    payload = b"%PDF-1.4 fake document bytes"
    path = file_store.store_document_bytes(1, "textbook", "book.pdf", payload, "application/pdf")
    assert path.startswith(file_store.REMOTE_PREFIX)

    loaded = file_store.load_document_bytes(_doc(file_path=path))
    assert loaded == payload
    # Exactly one object landed in the bucket, holding the raw bytes.
    assert len(r2.objects) == 1
    (key, body) = next(iter(r2.objects.items()))
    assert key.startswith("documents/1/textbook/")
    assert key.endswith(".pdf")
    assert body == payload


def test_load_prefers_r2_over_file_data(r2):
    remote = file_store.store_document_bytes(1, "workbook", "wb.pdf", b"remote-bytes")
    # Even when a stale DB copy exists, the R2 object wins.
    doc = _doc(file_path=remote, file_data=b"stale-db-bytes")
    assert file_store.load_document_bytes(doc) == b"remote-bytes"


def test_load_remote_missing_returns_none(r2):
    assert file_store.load_document_bytes(_doc(file_path="r2://documents/9/wb/nope.bin")) is None


def test_load_local_file(tmp_path):
    f = tmp_path / "local.pdf"
    f.write_bytes(b"local-file-bytes")
    doc = _doc(file_path=str(f))
    assert file_store.load_document_bytes(doc) == b"local-file-bytes"


def test_load_falls_back_to_file_data():
    doc = _doc(file_data=b"db-stored-bytes")
    assert file_store.load_document_bytes(doc) == b"db-stored-bytes"


def test_load_nothing_returns_none():
    assert file_store.load_document_bytes(_doc()) is None


def test_has_document_bytes():
    assert file_store.has_document_bytes(_doc(file_data=b"x")) is True
    assert file_store.has_document_bytes(_doc(file_path=f"r2://documents/1/textbook/a.pdf")) is True
    assert file_store.has_document_bytes(_doc()) is False


def test_delete_remote_path(r2):
    path = file_store.store_document_bytes(1, "textbook", "b.pdf", b"delete-me")
    assert file_store.load_document_bytes(_doc(file_path=path)) == b"delete-me"
    file_store.delete_document_path(path)
    assert file_store.load_document_bytes(_doc(file_path=path)) is None
    # Deleting a non-remote path is a silent no-op.
    file_store.delete_document_path("")