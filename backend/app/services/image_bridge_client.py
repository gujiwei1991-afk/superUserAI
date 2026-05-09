from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class BridgeFetchResult:
    url: str
    media_type: str
    size: int


class BridgeError(Exception):
    """Raised when the bridge call fails. `short` is a user-facing 1-line summary."""

    def __init__(self, short: str, detail: str = "") -> None:
        super().__init__(detail or short)
        self.short = short
        self.detail = detail


class ImageBridgeClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def fetch_image(
        self,
        cdn_key: str,
        aes_key: str,
        size: int,
        img_type: int,
        msg_id: str,
    ) -> BridgeFetchResult:
        if not self.settings.image_bridge_url:
            raise BridgeError(short="未配置 bridge", detail="image_bridge_url is empty")

        url = self.settings.image_bridge_url.rstrip("/") + "/fetch-image"
        headers = {"Content-Type": "application/json"}
        if self.settings.image_bridge_token:
            headers["X-Bridge-Token"] = self.settings.image_bridge_token

        payload = {
            "cdn_key": cdn_key,
            "aes_key": aes_key,
            "size": size,
            "img_type": img_type,
            "msg_id": msg_id,
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.image_bridge_timeout_seconds
            ) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise BridgeError(short="bridge 超时", detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise BridgeError(short="bridge 不可达", detail=str(exc)) from exc

        if response.status_code == 401:
            raise BridgeError(short="bridge token 错误", detail=response.text[:200])
        if response.status_code == 413:
            raise BridgeError(short="图太大", detail=response.text[:200])
        if response.status_code >= 500:
            raise BridgeError(
                short="bridge 内部错误",
                detail=f"HTTP {response.status_code}: {response.text[:200]}",
            )
        if response.status_code != 200:
            raise BridgeError(
                short=f"bridge HTTP {response.status_code}",
                detail=response.text[:200],
            )

        data = response.json()
        if not isinstance(data, dict) or "url" not in data:
            raise BridgeError(short="bridge 返回格式异常", detail=str(data)[:200])

        return BridgeFetchResult(
            url=data["url"],
            media_type=data.get("media_type", "image/jpeg"),
            size=int(data.get("size", size)),
        )
