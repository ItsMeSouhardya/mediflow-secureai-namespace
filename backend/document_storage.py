"""Encrypted document storage backends for MediFlow Secure.

Architecture
------------
Documents are NEVER stored as plaintext on disk or in object storage.
Envelope encryption is used:

  1. A per-file random AES-128 data-encryption key (DEK) is generated.
  2. The DEK is used to produce a Fernet token wrapping the plaintext bytes.
  3. The DEK itself is encrypted (key-wrapped) with the configured
     key-encryption key (KEK) identified by DOCUMENT_ENCRYPTION_KEY.
  4. Both the key-wrapped DEK and the Fernet ciphertext are written to
     storage as a single opaque blob:
         [4-byte big-endian wrapped-DEK length][wrapped DEK][ciphertext]

This means:
  - The KEK never touches the stored bytes; only key IDs are recorded.
  - Rotating the KEK only requires re-wrapping the stored DEKs (not
    re-encrypting all document bytes).
  - Decryption requires both the stored blob and a live KEK.

Public interface
----------------
``get_storage_backend(config)`` returns the active backend instance.

Both backends implement:
  ``store(plaintext_bytes) -> StorageRef``
  ``retrieve(storage_key) -> bytes``   (returns plaintext)
  ``delete(storage_key) -> None``

``StorageRef`` carries the opaque storage_key, storage_backend label, and
encryption_key_id.  The key_id is recorded in DocumentVersion so the
correct KEK can be selected during decryption even after key rotation.
"""

from __future__ import annotations

import io
import os
import struct
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from errors import ApiProblem


# ---------------------------------------------------------------------------
# Key management helpers
# ---------------------------------------------------------------------------

def _build_multi_fernet(config: dict) -> tuple[MultiFernet, str]:
    """Return a MultiFernet that can decrypt with any configured KEK.

    Returns the MultiFernet instance and the *primary* key ID (used when
    encrypting new documents).  The primary key is always the first one in
    the MultiFernet so it is used for all new encryptions.

    Key IDs are the first 16 hex chars of the key material's SHA-256 digest,
    providing a stable, non-secret identifier for key rotation bookkeeping.
    """
    import hashlib

    primary_raw = config.get("DOCUMENT_ENCRYPTION_KEY", "")
    if not primary_raw:
        # No key configured — generate a temporary in-process key so the
        # application starts in development without configuration.  Files
        # encrypted with this key are lost on restart: acceptable for local
        # dev, but the startup validator warns loudly.
        primary_raw = Fernet.generate_key().decode()

    keys: list[Fernet] = []
    key_ids: list[str] = []

    for raw in [primary_raw]:
        bkey = raw.encode() if isinstance(raw, str) else raw
        kid = hashlib.sha256(bkey).hexdigest()[:16]
        keys.append(Fernet(bkey))
        key_ids.append(kid)

    # Add previous key (for rotation) if configured.
    prev_raw = config.get("DOCUMENT_ENCRYPTION_KEY_PREV", "")
    if prev_raw:
        bkey = prev_raw.encode() if isinstance(prev_raw, str) else prev_raw
        kid = hashlib.sha256(bkey).hexdigest()[:16]
        keys.append(Fernet(bkey))
        key_ids.append(kid)

    return MultiFernet(keys), key_ids[0]


# ---------------------------------------------------------------------------
# Envelope encryption / decryption
# ---------------------------------------------------------------------------

def _envelope_encrypt(plaintext: bytes, multi_fernet: MultiFernet) -> bytes:
    """Encrypt plaintext using envelope encryption.

    Layout of the returned blob:
        [4 bytes big-endian: len(wrapped_dek)][wrapped_dek][fernet_ciphertext]
    """
    # Generate a fresh DEK for this document.
    dek = Fernet.generate_key()
    fernet_dek = Fernet(dek)

    # Encrypt plaintext with the DEK.
    ciphertext = fernet_dek.encrypt(plaintext)

    # Wrap the DEK with the KEK (MultiFernet uses the primary key).
    wrapped_dek = multi_fernet.encrypt(dek)

    # Assemble the blob.
    header = struct.pack(">I", len(wrapped_dek))
    return header + wrapped_dek + ciphertext


def _envelope_decrypt(blob: bytes, multi_fernet: MultiFernet) -> bytes:
    """Decrypt an envelope-encrypted blob and return plaintext."""
    if len(blob) < 4:
        raise ApiProblem("document_corrupt", "Stored document blob is too short", 500)

    (wrapped_dek_len,) = struct.unpack(">I", blob[:4])
    if len(blob) < 4 + wrapped_dek_len:
        raise ApiProblem("document_corrupt", "Stored document blob is malformed", 500)

    wrapped_dek = blob[4 : 4 + wrapped_dek_len]
    ciphertext = blob[4 + wrapped_dek_len :]

    try:
        dek = multi_fernet.decrypt(wrapped_dek)
    except InvalidToken as exc:
        raise ApiProblem(
            "document_decryption_failed",
            "Document key could not be decrypted — the KEK may have been rotated without preserving the previous key",
            500,
        ) from exc

    fernet_dek = Fernet(dek)
    try:
        return fernet_dek.decrypt(ciphertext)
    except InvalidToken as exc:
        raise ApiProblem(
            "document_decryption_failed",
            "Document content could not be decrypted",
            500,
        ) from exc


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StorageRef:
    """Opaque reference returned after a successful store operation."""

    storage_key: str       # path fragment (local) or object key (S3)
    storage_backend: str   # "local" | "s3"
    encryption_key_id: str # first 16 hex chars of KEK SHA-256 — non-secret


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------

class StorageBackend(Protocol):
    def store(self, plaintext_bytes: bytes) -> StorageRef:
        """Encrypt and persist plaintext_bytes; return an opaque StorageRef."""
        ...

    def retrieve(self, storage_key: str) -> bytes:
        """Retrieve and decrypt document bytes; raise ApiProblem on failure."""
        ...

    def delete(self, storage_key: str) -> None:
        """Remove a stored object.  Idempotent — does not raise if missing."""
        ...


# ---------------------------------------------------------------------------
# Local filesystem backend (development / single-node deployment)
# ---------------------------------------------------------------------------

class LocalEncryptedStorage:
    """Stores encrypted document blobs under a configured base directory.

    Directory layout::

        <DOCUMENT_STORAGE_PATH>/
            <first 2 hex chars of UUID>/     ← sharding to avoid huge dirs
                <UUID>.enc

    Files are never accessible via HTTP; they sit outside the web root.
    """

    BACKEND_LABEL = "local"

    def __init__(self, base_path: str | Path, multi_fernet: MultiFernet, key_id: str) -> None:
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)
        self._mf = multi_fernet
        self._key_id = key_id

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def store(self, plaintext_bytes: bytes) -> StorageRef:
        blob = _envelope_encrypt(plaintext_bytes, self._mf)
        object_name = f"{uuid.uuid4().hex}.enc"
        shard = object_name[:2]
        shard_dir = self._base / shard
        shard_dir.mkdir(exist_ok=True)
        dest = shard_dir / object_name
        dest.write_bytes(blob)
        storage_key = f"{shard}/{object_name}"
        return StorageRef(
            storage_key=storage_key,
            storage_backend=self.BACKEND_LABEL,
            encryption_key_id=self._key_id,
        )

    def retrieve(self, storage_key: str) -> bytes:
        path = self._base / storage_key
        if not path.exists():
            raise ApiProblem("document_not_found", "Stored document file is missing", 500)
        blob = path.read_bytes()
        return _envelope_decrypt(blob, self._mf)

    def delete(self, storage_key: str) -> None:
        path = self._base / storage_key
        try:
            path.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# S3-compatible backend (production / MinIO / LocalStack)
# ---------------------------------------------------------------------------

class S3EncryptedStorage:
    """Stores encrypted document blobs in an S3-compatible object store.

    Encryption is identical to the local backend — the S3 bucket holds
    only the opaque envelope blobs.  No server-side encryption is relied
    upon so security is independent of bucket ACLs.

    boto3 is an optional runtime dependency; import is deferred so the
    application starts without it in environments using only local storage.
    """

    BACKEND_LABEL = "s3"

    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        multi_fernet: MultiFernet,
        key_id: str,
    ) -> None:
        try:
            import boto3  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for S3 storage — install it: pip install boto3"
            ) from exc

        self._bucket = bucket
        self._mf = multi_fernet
        self._key_id = key_id

        kwargs: dict = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if access_key and secret_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key

        self._s3 = boto3.client("s3", **kwargs)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def store(self, plaintext_bytes: bytes) -> StorageRef:
        blob = _envelope_encrypt(plaintext_bytes, self._mf)
        object_key = f"documents/{uuid.uuid4().hex}.enc"
        self._s3.put_object(
            Bucket=self._bucket,
            Key=object_key,
            Body=blob,
            ContentType="application/octet-stream",
            # Disable public access at the object level.
            ACL="private",
        )
        return StorageRef(
            storage_key=object_key,
            storage_backend=self.BACKEND_LABEL,
            encryption_key_id=self._key_id,
        )

    def retrieve(self, storage_key: str) -> bytes:
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=storage_key)
            blob = response["Body"].read()
        except self._s3.exceptions.NoSuchKey:
            raise ApiProblem("document_not_found", "Stored document object is missing", 500)
        return _envelope_decrypt(blob, self._mf)

    def delete(self, storage_key: str) -> None:
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=storage_key)
        except Exception:  # noqa: BLE001 — S3 delete is best-effort
            pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_storage_backend(config: dict) -> LocalEncryptedStorage | S3EncryptedStorage:
    """Return the configured storage backend, initialised with KEK material.

    Called once per request (or cached) from document_service — never
    instantiate backends directly in route handlers.
    """
    multi_fernet, key_id = _build_multi_fernet(config)
    backend_name = config.get("DOCUMENT_STORAGE_BACKEND", "local")

    if backend_name == "s3":
        return S3EncryptedStorage(
            bucket=config["DOCUMENT_S3_BUCKET"],
            region=config.get("DOCUMENT_S3_REGION", "us-east-1"),
            endpoint_url=config.get("DOCUMENT_S3_ENDPOINT_URL", ""),
            access_key=config.get("DOCUMENT_S3_ACCESS_KEY", ""),
            secret_key=config.get("DOCUMENT_S3_SECRET_KEY", ""),
            multi_fernet=multi_fernet,
            key_id=key_id,
        )

    return LocalEncryptedStorage(
        base_path=config.get("DOCUMENT_STORAGE_PATH", "document_store"),
        multi_fernet=multi_fernet,
        key_id=key_id,
    )


# ---------------------------------------------------------------------------
# Startup validator — called from app factory
# ---------------------------------------------------------------------------

def validate_storage_config(config: dict) -> list[str]:
    """Return a list of configuration warnings (empty = all good).

    Does not raise so the app can start in development with degraded config
    while making the operator aware of the issues.
    """
    warnings: list[str] = []

    if not config.get("DOCUMENT_ENCRYPTION_KEY"):
        warnings.append(
            "DOCUMENT_ENCRYPTION_KEY is not set — a temporary in-process key is being used. "
            "Documents encrypted now will be UNRECOVERABLE after restart. "
            "Set a persistent Fernet key before uploading any real documents."
        )

    backend = config.get("DOCUMENT_STORAGE_BACKEND", "local")
    if backend == "s3" and not config.get("DOCUMENT_S3_BUCKET"):
        warnings.append(
            "DOCUMENT_STORAGE_BACKEND=s3 but DOCUMENT_S3_BUCKET is not configured."
        )

    return warnings
