"""
File storage for uploaded files (project PDFs): a private S3 bucket.

Routes depend on the :class:`FileStorage` interface only, through ``FileStorageDep``;
:func:`get_file_storage` returns the process-wide :class:`S3FileStorage` (tests override it).
The contract is described in ``app/services/README.md``.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import cache
from pathlib import PurePosixPath
from typing import Annotated, Any, AsyncIterator, BinaryIO

import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.exceptions import DependencyUnavailable

CHUNK_SIZE = 64 * 1024
_MISSING_KEY_CODES = {"NoSuchKey", "404", "NotFound"}


@dataclass(frozen=True)
class StoredFile:
    """Result of :meth:`FileStorage.save`."""
    key: str
    size_bytes: int
    content_type: str


class FileStorage(ABC):
    """
    Stores files under opaque keys such as ``projects/1/<uuid>.pdf``.
    The key is what the database keeps (``project_documents.file_path``).

    Keys are relative POSIX paths built by the backend: ``/``-separated, no leading
    ``/``, no ``.``/``..`` segments. Implementations reject anything else with ``ValueError``.
    Storage failures raise :class:`DependencyUnavailable` (503).
    """

    @abstractmethod
    async def save(self, key: str, stream: BinaryIO, content_type: str) -> StoredFile:
        """Writes ``stream`` (read from its current position to EOF) under ``key``,
        replacing an existing file with that key."""

    @abstractmethod
    async def open(self, key: str) -> AsyncIterator[bytes]:
        """Returns the file's content as an async iterator of chunks.
        :raises FileNotFoundError: no file with this key (raised by this call, before iteration)."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Removes the file. A missing file is not an error."""


def validate_key(key: str) -> PurePosixPath:
    path = PurePosixPath(key)
    if not key or key.startswith("/") or "\\" in key or any(p in ("", ".", "..") for p in key.split("/")):
        raise ValueError(f"Invalid storage key {key!r}.")
    return path


def _unavailable() -> DependencyUnavailable:
    return DependencyUnavailable(msg="File storage is unavailable.")


class S3FileStorage(FileStorage):
    """
    Files in a private S3-compatible bucket (SeaweedFS in Compose). The API streams them to
    the client after its own access check, so the bucket never needs public or presigned access.
    The boto3 client is created on first use from the ``S3_*`` settings, or passed in (tests).
    """

    def __init__(self, bucket: str, client: Any = None):
        self.bucket = bucket
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            if not (settings.s3_endpoint_url and settings.s3_access_key_id and settings.s3_secret_access_key):
                raise DependencyUnavailable(msg="File storage is not configured.")
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                region_name=settings.s3_region,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                config=Config(
                    s3={"addressing_style": "path"}, connect_timeout=5, read_timeout=30,
                    retries={"max_attempts": 2},
                ),
            )
        return self._client

    async def save(self, key: str, stream: BinaryIO, content_type: str) -> StoredFile:
        validate_key(key)
        start = stream.tell()
        size = stream.seek(0, 2) - start
        stream.seek(start)
        try:
            await run_in_threadpool(
                self.client.upload_fileobj, stream, self.bucket, key,
                ExtraArgs={"ContentType": content_type, "ContentDisposition": "inline"},
            )
        except (BotoCoreError, ClientError, S3UploadFailedError):
            raise _unavailable() from None
        return StoredFile(key=key, size_bytes=size, content_type=content_type)

    async def open(self, key: str) -> AsyncIterator[bytes]:
        validate_key(key)
        try:
            response = await run_in_threadpool(self.client.get_object, Bucket=self.bucket, Key=key)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in _MISSING_KEY_CODES:
                raise FileNotFoundError(key) from None
            raise _unavailable() from None
        except BotoCoreError:
            raise _unavailable() from None
        body = response["Body"]

        async def chunks() -> AsyncIterator[bytes]:
            try:
                while chunk := await run_in_threadpool(body.read, CHUNK_SIZE):
                    yield chunk
            finally:
                body.close()

        return chunks()

    async def delete(self, key: str) -> None:
        validate_key(key)
        try:
            # S3 deletes are idempotent: a missing key is not an error.
            await run_in_threadpool(self.client.delete_object, Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError):
            raise _unavailable() from None


@cache
def get_file_storage() -> FileStorage:
    """Dependency returning the shared :class:`S3FileStorage` for ``S3_BUCKET``."""
    return S3FileStorage(settings.s3_bucket)


FileStorageDep = Annotated[FileStorage, Depends(get_file_storage)]
