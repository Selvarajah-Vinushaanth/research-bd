# ============================================
# Service - Google Cloud Storage
# ============================================

from __future__ import annotations

import datetime
from typing import Optional

import structlog
from google.cloud import storage
from google.oauth2 import service_account

from app.config import settings

logger = structlog.get_logger()


class GCSService:
    """
    Service for interacting with Google Cloud Storage.
    Handles PDF upload, download, signed URL generation, and deletion.
    """

    _instance: Optional[GCSService] = None

    def __new__(cls) -> GCSService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        try:
            if settings.GCP_CREDENTIALS_PATH:
                credentials = service_account.Credentials.from_service_account_file(
                    settings.GCP_CREDENTIALS_PATH
                )
                self._client = storage.Client(
                    credentials=credentials, project=settings.GCP_PROJECT_ID
                )
            else:
                # Falls back to GOOGLE_APPLICATION_CREDENTIALS env var or default credentials
                self._client = storage.Client(project=settings.GCP_PROJECT_ID or None)

            self._bucket_name = settings.GCP_BUCKET_NAME
            self._bucket = self._client.bucket(self._bucket_name)

            # Create bucket if it doesn't exist
            if not self._bucket.exists():
                self._bucket = self._client.create_bucket(
                    self._bucket_name, location="us-central1"
                )
                logger.info("gcs_bucket_created", bucket=self._bucket_name)

            logger.info("gcs_service_initialized", bucket=self._bucket_name)

        except Exception as e:
            logger.error("gcs_service_init_failed", error=str(e))
            self._client = None
            self._bucket = None

    @property
    def is_available(self) -> bool:
        """Check if GCS is properly configured and ready."""
        return self._client is not None and self._bucket is not None

    def upload_file(
        self,
        file_content: bytes,
        destination_path: str,
        content_type: str = "application/pdf",
    ) -> str:
        """
        Upload a file to GCS.

        Args:
            file_content: Raw file bytes.
            destination_path: Path within the bucket (e.g., 'papers/user_id/hash.pdf').
            content_type: MIME type of the file.

        Returns:
            The GCS path (relative to bucket).

        Raises:
            RuntimeError: If GCS is not configured.
        """
        if not self.is_available:
            raise RuntimeError(
                "GCS is not configured. Set GCP_CREDENTIALS_PATH and GCP_BUCKET_NAME in .env"
            )

        blob = self._bucket.blob(destination_path)
        blob.upload_from_string(file_content, content_type=content_type)

        logger.info(
            "gcs_file_uploaded",
            path=destination_path,
            size_bytes=len(file_content),
            bucket=self._bucket_name,
        )
        return destination_path

    def download_file(self, source_path: str) -> bytes:
        """
        Download a file from GCS.

        Args:
            source_path: Path within the bucket.

        Returns:
            Raw file bytes.

        Raises:
            RuntimeError: If GCS is not configured.
            FileNotFoundError: If file does not exist in GCS.
        """
        if not self.is_available:
            raise RuntimeError("GCS is not configured.")

        blob = self._bucket.blob(source_path)
        if not blob.exists():
            raise FileNotFoundError(f"File not found in GCS: {source_path}")

        content = blob.download_as_bytes()
        logger.info("gcs_file_downloaded", path=source_path, size_bytes=len(content))
        return content

    def get_signed_url(self, file_path: str, expiration_minutes: int = 60) -> str:
        """
        Generate a time-limited signed URL for direct file access.

        Args:
            file_path: Path within the bucket.
            expiration_minutes: How long the URL remains valid (default: 60 min).

        Returns:
            Signed URL string.
        """
        if not self.is_available:
            raise RuntimeError("GCS is not configured.")

        blob = self._bucket.blob(file_path)
        url = blob.generate_signed_url(
            expiration=datetime.timedelta(minutes=expiration_minutes),
            method="GET",
        )
        logger.info(
            "gcs_signed_url_generated", path=file_path, expires_in_min=expiration_minutes
        )
        return url

    def delete_file(self, file_path: str) -> bool:
        """
        Delete a file from GCS.

        Args:
            file_path: Path within the bucket.

        Returns:
            True if deleted, False if file didn't exist or GCS unavailable.
        """
        if not self.is_available:
            logger.warning("gcs_not_configured_skip_delete", path=file_path)
            return False

        blob = self._bucket.blob(file_path)
        if blob.exists():
            blob.delete()
            logger.info("gcs_file_deleted", path=file_path)
            return True
        return False

    def file_exists(self, file_path: str) -> bool:
        """Check if a file exists in GCS."""
        if not self.is_available:
            return False
        blob = self._bucket.blob(file_path)
        return blob.exists()


def get_gcs_service() -> GCSService:
    """Get or create the GCS service singleton."""
    return GCSService()
