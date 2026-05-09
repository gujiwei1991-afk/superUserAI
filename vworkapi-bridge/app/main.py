from __future__ import annotations

import logging
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.qiniu_uploader import QiniuUploadError, QiniuUploader
from app.tmp_storage import TmpStorage
from app.vworkapi_client import VWorkApiClient, VWorkApiError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class FetchImageRequest(BaseModel):
    cdn_key: str = Field(min_length=1)
    aes_key: str = Field(min_length=1)
    size: int = Field(ge=1)
    img_type: int = Field(default=2)
    msg_id: str = Field(min_length=1)


class FetchImageResponse(BaseModel):
    url: str
    media_type: str
    size: int


def _build_app() -> FastAPI:
    app = FastAPI(title="vworkapi-bridge", version="0.1.0")

    settings = get_settings()
    storage = TmpStorage(settings.tmp_dir)
    vw_client = VWorkApiClient(settings.vworkapi_host, settings.vworkapi_port)
    uploader = QiniuUploader(
        settings.qiniu_ak, settings.qiniu_sk,
        settings.qiniu_bucket, settings.qiniu_domain,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/fetch-image", response_model=FetchImageResponse)
    async def fetch_image(
        req: FetchImageRequest,
        x_bridge_token: Annotated[str | None, Header(alias="X-Bridge-Token")] = None,
    ) -> FetchImageResponse:
        if settings.image_bridge_token and x_bridge_token != settings.image_bridge_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad token")

        if req.size > settings.max_image_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"error": "image_too_large",
                        "size": req.size,
                        "limit": settings.max_image_bytes},
            )

        tmp_path = storage.allocate(req.msg_id)
        try:
            try:
                await vw_client.download_image(
                    cdn_key=req.cdn_key, aes_key=req.aes_key,
                    size=req.size, img_type=req.img_type,
                    save_path=str(tmp_path),
                )
            except VWorkApiError as exc:
                logger.warning("vworkapi 9001 failed: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={"error": f"vworkapi_9001_failed: {exc}"},
                ) from exc

            try:
                url, media_type = await uploader.upload(tmp_path, key_prefix="sua/")
            except QiniuUploadError as exc:
                logger.warning("qiniu upload failed: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail={"error": f"qiniu_upload_failed: {exc}"},
                ) from exc

            actual_size = tmp_path.stat().st_size if tmp_path.exists() else req.size
            return FetchImageResponse(url=url, media_type=media_type, size=actual_size)
        finally:
            storage.cleanup(tmp_path)

    return app


app = _build_app()
