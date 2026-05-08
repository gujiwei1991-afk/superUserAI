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

    async def send_at_group(
        self,
        chat_room_id: str,
        at_list: list[str],
        msg: str,
    ) -> dict[str, Any]:
        # vworkApi 群发并 @ 群成员: type=3009, chat_room_id, at_list, msg
        # msg 文本里需要把 @昵称 也写好,DLL 不会自动拼接 — 调用方负责。
        return await self._post(
            {
                "type": VWorkSendType.SEND_AT_GROUP.value,
                "chat_room_id": chat_room_id,
                "at_list": at_list,
                "msg": msg,
            }
        )

    async def send_card_link(
        self,
        user_id: str,
        title: str,
        desc: str,
        target_url: str,
        cover_url: str = "",
    ) -> dict[str, Any]:
        return await self._post(
            {
                "type": VWorkSendType.SEND_CARD_LINK.value,
                "user_id": user_id,
                "title": title,
                "desc": desc,
                "target_url": target_url,
                "cover_url": cover_url,
            }
        )

    async def send_file(self, user_id: str, path: str) -> dict[str, Any]:
        return await self._post(
            {
                "type": VWorkSendType.SEND_FILE.value,
                "user_id": user_id,
                "path": path,
            }
        )

    async def list_internal_friends(
        self,
        page_size: int = 100,
        max_pages: int = 200,
    ) -> list[dict[str, Any]]:
        """拉取所有内部好友（同事）。vworkApi type=2001, 自动翻页直到取尽。"""
        all_items: list[dict[str, Any]] = []
        page_num = 1
        while page_num <= max_pages:
            payload = {"type": 2001, "page_num": page_num, "page_size": page_size}
            response = await self._post(payload)
            data = response.get("data") or {}
            items = data.get("list") or []
            if not isinstance(items, list):
                break
            all_items.extend(item for item in items if isinstance(item, dict))

            total_page = data.get("total_page")
            if not isinstance(total_page, int) or page_num >= total_page or not items:
                break
            page_num += 1
        return all_items

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not hasattr(self, "_client"):
            self._client = httpx.AsyncClient(timeout=10.0)
        response = await self._client.post(self.base_url, json=payload)
        response.raise_for_status()
        return response.json()
