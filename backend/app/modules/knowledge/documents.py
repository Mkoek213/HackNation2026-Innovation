"""Private S3 objects; public access is mediated by the knowledge router."""
import uuid
from pathlib import Path

import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .errors import KnowledgeUnavailable
from .schemas import DocumentRole, StoredDocument
from .settings import KnowledgeSettings

CONTENT_TYPES = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


class DocumentStorage:
    def __init__(self, settings: KnowledgeSettings):
        self.settings = settings
        self._client = None

    @property
    def client(self):
        if self._client is None:
            s = self.settings
            if not (s.s3_endpoint_url and s.s3_access_key and s.s3_secret_key):
                raise KnowledgeUnavailable("Document storage is not configured.")
            self._client = boto3.client(
                "s3", endpoint_url=s.s3_endpoint_url, region_name=s.s3_region,
                aws_access_key_id=s.s3_access_key, aws_secret_access_key=s.s3_secret_key,
                config=Config(s3={"addressing_style": "path"}, connect_timeout=5, read_timeout=30,
                              retries={"max_attempts": 2}),
            )
        return self._client

    def describe(self, innovation_id: str, path: Path, role: DocumentRole = "full") -> StoredDocument:
        document_id = uuid.uuid4().hex
        return StoredDocument(
            id=document_id, role=role, filename=path.name, content_type=CONTENT_TYPES[path.suffix.lower()],
            size_bytes=path.stat().st_size, object_key=f"innovations/{innovation_id}/{document_id}",
            download_url=f"/api/v1/knowledge/innovations/{innovation_id}/documents/{document_id}",
        )

    def upload(self, path: Path, document: StoredDocument) -> None:
        try:
            self.client.upload_file(str(path), self.settings.s3_bucket, document.object_key,
                                    ExtraArgs={"ContentType": document.content_type})
        except (BotoCoreError, ClientError, S3UploadFailedError) as e:
            raise KnowledgeUnavailable("Document storage is unavailable.") from e

    def open(self, document: StoredDocument):
        try:
            return self.client.get_object(Bucket=self.settings.s3_bucket, Key=document.object_key)["Body"]
        except ClientError as e:
            if e.response["Error"]["Code"] in {"NoSuchKey", "404"}:
                raise FileNotFoundError(document.id) from e
            raise KnowledgeUnavailable("Document storage is unavailable.") from e
        except BotoCoreError as e:
            raise KnowledgeUnavailable("Document storage is unavailable.") from e

    def delete(self, documents: list[StoredDocument]) -> None:
        for document in documents:
            self.client.delete_object(Bucket=self.settings.s3_bucket, Key=document.object_key)
