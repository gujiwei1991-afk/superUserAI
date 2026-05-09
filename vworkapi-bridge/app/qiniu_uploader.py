from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

from qiniu import Auth, put_file  # type: ignore

logger = logging.getLogger(__name__)


class QiniuUploadError(Exception):
    pass


class QiniuUploader:
    def __init__(self, ak: str, sk: str, bucket: str, domain: str) -> None:
        if not (ak and sk and bucket and domain):
            raise QiniuUploadError("qiniu credentials/bucket/domain not configured")
        self.bucket = bucket
        self.domain = domain.rstrip("/")
        self.auth = Auth(ak, sk)

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 64)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _detect_media_type(path: Path) -> tuple[str, str]:
        """Sniff file format from magic bytes. Replaces stdlib imghdr removed in 3.13."""
        with path.open("rb") as f:
            head = f.read(16)
        if head.startswith(b"\xff\xd8\xff"):
            return "jpg", "image/jpeg"
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png", "image/png"
        if head[:6] in (b"GIF87a", b"GIF89a"):
            return "gif", "image/gif"
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            return "webp", "image/webp"
        # Default to jpeg — vworkApi gives high-quality WeChat images that are
        # almost always JPEG even when the extension says otherwise.
        return "jpg", "image/jpeg"

    async def upload(self, path: Path, key_prefix: str = "sua/") -> tuple[str, str]:
        if not path.exists():
            raise QiniuUploadError(f"file not found: {path}")

        loop = asyncio.get_running_loop()
        ext, media_type = await loop.run_in_executor(None, self._detect_media_type, path)
        sha = await loop.run_in_executor(None, self._sha256, path)
        key = f"{key_prefix}{sha}.{ext}"

        token = self.auth.upload_token(self.bucket, key, 3600)

        def _do_put() -> tuple[dict | None, object]:
            return put_file(token, key, str(path))

        ret, info = await loop.run_in_executor(None, _do_put)
        status = getattr(info, "status_code", None)
        if status != 200 or not ret or "key" not in ret:
            raise QiniuUploadError(
                f"qiniu upload failed: status={status} info={info} ret={ret}"
            )
        return f"{self.domain}/{ret['key']}", media_type
