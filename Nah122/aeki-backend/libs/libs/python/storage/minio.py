import os
import json
import io
from minio import Minio
from typing import Any, Dict

class MinioWrapper:
    """
    Wrapper around Minio client for standardized object storage.
    Works with local MinIO, Backblaze B2, Cloudflare R2, and any S3-compatible store.
    SSL is enabled automatically when MINIO_USE_SSL=true.
    """
    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str = "admin",
        secret_key: str = "password",
        secure: bool = None,  # None = auto-detect from env
    ):
        if secure is None:
            secure = os.getenv("MINIO_USE_SSL", "false").lower() == "true"

        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    def ensure_bucket(self, bucket_name: str):
        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name)

    def upload_json(self, bucket_name: str, object_name: str, data: Dict[str, Any]):
        try:
            self.ensure_bucket(bucket_name)

            def json_serializer(obj):
                if hasattr(obj, 'isoformat'):
                    return obj.isoformat()
                return str(obj)

            json_data = json.dumps(data, indent=2, default=json_serializer).encode('utf-8')
            json_stream = io.BytesIO(json_data)
            self.client.put_object(
                bucket_name,
                object_name,
                json_stream,
                length=len(json_data),
                content_type="application/json",
            )
        except Exception as e:
            print(f"❌ Error uploading to MinIO/B2: {e}")
