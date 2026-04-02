from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings
from shared.constants import VWorkSendType


class WeChatClient:
    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        settings = get_settings()
        self.host = host or settings.vwork_api_host
        self.port = port or settings.vwork_api_port
        self.base_url = f"http://{self.host}:{self.port}/api"

    async def send_text(self, user_id: str, msg: str) -> dict[str, Any]:
        return await self._post(
            {
                "type": VWorkSendType.SEND_TEXT.value,
                "user_id": user_id,
                "msg": msg,
            }
        )

    async def send_card_link(
        self,
        user_id: str,
        title: str,
        desc: str,
        url: str,
        cover_url: str = "",
    ) -> dict[str, Any]:
        return await self._post(
            {
                "type": VWorkSendType.SEND_CARD_LINK.value,
                "user_id": user_id,
                "title": title,
                "desc": desc,
                "url": url,
                "cover_url": cover_url,
            }
        )

    async def send_file(self, user_id: str, file_path: str) -> dict[str, Any]:
        return await self._post(
            {
                "type": VWorkSendType.SEND_FILE.value,
                "user_id": user_id,
                "file_path": file_path,
            }
        )

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not hasattr(self, "_client"):
            self._client = httpx.AsyncClient(timeout=10.0)
        response = await self._client.post(self.base_url, json=payload)
        response.raise_for_status()
        return response.json()
