"""End-to-end smoke for vworkapi-bridge.

Mocks vworkApi 9001 and the Qiniu uploader so it runs without external
services. Uses FastAPI's TestClient.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Provide minimal env so QiniuUploader.__init__ doesn't blow up.
os.environ.setdefault("QINIU_AK", "ak")
os.environ.setdefault("QINIU_SK", "sk")
os.environ.setdefault("QINIU_BUCKET", "bkt")
os.environ.setdefault("QINIU_DOMAIN", "https://cdn.example.com")
os.environ.setdefault("IMAGE_BRIDGE_TOKEN", "secret")
os.environ.setdefault("TMP_DIR", "/tmp/sua-bridge-test")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.qiniu_uploader import QiniuUploader  # noqa: E402
from app.vworkapi_client import VWorkApiClient  # noqa: E402


client = TestClient(app)


def test_healthz() -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    print("healthz ok")


def test_unauthorized() -> None:
    r = client.post("/fetch-image", json={
        "cdn_key": "a", "aes_key": "b", "size": 100, "img_type": 2, "msg_id": "m1",
    })
    assert r.status_code == 401, r.text
    print("unauthorized ok")


def test_payload_too_large() -> None:
    r = client.post("/fetch-image",
        headers={"X-Bridge-Token": "secret"},
        json={"cdn_key": "a", "aes_key": "b", "size": 99999999999,
              "img_type": 2, "msg_id": "m2"})
    assert r.status_code == 413, r.text
    print("too large ok")


async def _fake_download_ok(self, *, cdn_key, aes_key, size, img_type, save_path):
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    Path(save_path).write_bytes(b"\xff\xd8\xff\xe0fake-jpg-bytes")


async def _fake_upload_ok(self, path, key_prefix="sua/"):
    return ("https://cdn.example.com/sua/abc.jpg", "image/jpeg")


async def _fake_download_fail(self, *, cdn_key, aes_key, size, img_type, save_path):
    from app.vworkapi_client import VWorkApiError
    raise VWorkApiError("simulated vworkapi crash")


def test_happy_path() -> None:
    with patch.object(VWorkApiClient, "download_image", _fake_download_ok), \
         patch.object(QiniuUploader, "upload", _fake_upload_ok):
        r = client.post(
            "/fetch-image",
            headers={"X-Bridge-Token": "secret"},
            json={"cdn_key": "a", "aes_key": "b", "size": 100,
                  "img_type": 2, "msg_id": "m3"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"] == "https://cdn.example.com/sua/abc.jpg"
    assert body["media_type"] == "image/jpeg"
    print("happy path ok")


def test_vworkapi_failure_502() -> None:
    with patch.object(VWorkApiClient, "download_image", _fake_download_fail):
        r = client.post(
            "/fetch-image",
            headers={"X-Bridge-Token": "secret"},
            json={"cdn_key": "a", "aes_key": "b", "size": 100,
                  "img_type": 2, "msg_id": "m4"},
        )
    assert r.status_code == 502, r.text
    print("vworkapi 502 ok")


def main() -> None:
    test_healthz()
    test_unauthorized()
    test_payload_too_large()
    test_happy_path()
    test_vworkapi_failure_502()
    print("\nall e2e_bridge checks passed")


if __name__ == "__main__":
    main()
