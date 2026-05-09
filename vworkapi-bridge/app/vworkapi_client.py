from __future__ import annotations

import httpx


class VWorkApiError(Exception):
    pass


class VWorkApiClient:
    def __init__(self, host: str, port: int) -> None:
        self.url = f"http://{host}:{port}/api"

    async def download_image(
        self,
        cdn_key: str,
        aes_key: str,
        size: int,
        img_type: int,
        save_path: str,
    ) -> None:
        payload = {
            "type": 9001,
            "cdn_key": cdn_key,
            "aes_key": aes_key,
            "size": size,
            "img_type": img_type,
            "save_path": save_path,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(self.url, json=payload)
            except httpx.HTTPError as exc:
                raise VWorkApiError(f"http error: {exc}") from exc

        if response.status_code != 200:
            raise VWorkApiError(f"vworkapi HTTP {response.status_code}: {response.text[:200]}")

        data = response.json()
        if data.get("errno") != 0:
            raise VWorkApiError(
                f"vworkapi errno={data.get('errno')} errmsg={data.get('errmsg')}"
            )
