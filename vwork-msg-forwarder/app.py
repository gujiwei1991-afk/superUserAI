"""vwork 消息转发器（部署在 vworkApi DLL 所在的 Windows 机器上）。

背景：vworkApi 的 DLL 收到微信消息后，固定 POST 到本机 127.0.0.1:9000/msg
（接收服务必须与 DLL 同机）。但 SuperUserAI 后端跑在另一台 Mac mini 上、藏在
家庭 NAT 后，DLL 够不到。本转发器监听 :9000/msg，把消息原样转发到后端
（经 cloudflared 隧道）。

自愈：隧道重启会换 URL。本服务提供 POST /set-target（密钥保护），Mac mini 端的
cloudflared 包装脚本在隧道起来后会调用它，把新的 /msg 地址推过来——无需人工改。
目标地址持久化到 target.txt，重启不丢。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

try:  # 可选：自动读取同目录 .env
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vwork-forwarder")

TARGET_FILE = Path(os.getenv("TARGET_FILE", "target.txt"))
INITIAL_TARGET = os.getenv("TARGET_MSG_URL", "").strip()
SET_SECRET = os.getenv("FORWARD_SECRET", "").strip()
FORWARD_TIMEOUT = float(os.getenv("FORWARD_TIMEOUT", "10"))


def _load_target() -> str:
    if TARGET_FILE.exists():
        t = TARGET_FILE.read_text(encoding="utf-8").strip()
        if t:
            return t
    return INITIAL_TARGET


def _save_target(url: str) -> None:
    TARGET_FILE.write_text(url, encoding="utf-8")


app = FastAPI(title="vwork-msg-forwarder")
_state = {"target": _load_target()}
log.info("startup target = %s", _state["target"] or "(未配置)")


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "target": _state["target"]}


@app.post("/msg")
async def forward_msg(request: Request) -> dict:
    """DLL 把微信消息 POST 到这里 → 原样转发到后端 /msg。"""
    body = await request.body()
    target = _state["target"]
    if not target:
        log.warning("no target configured; dropping message")
        return {"ok": False, "reason": "no target configured"}
    try:
        async with httpx.AsyncClient(timeout=FORWARD_TIMEOUT) as client:
            resp = await client.post(
                target, content=body, headers={"Content-Type": "application/json"}
            )
        log.info("forwarded -> %s [%s]", target, resp.status_code)
    except Exception as exc:  # 转发失败也回 200，避免 DLL 重试风暴
        log.exception("forward failed: %s", exc)
    return {"ok": True}


@app.post("/set-target")
async def set_target(
    request: Request, x_forward_secret: str = Header(default="")
) -> dict:
    """Mac mini 隧道起来后调用，更新转发目标（密钥保护 + 持久化）。"""
    if not SET_SECRET or x_forward_secret != SET_SECRET:
        raise HTTPException(status_code=403, detail="bad or missing secret")
    data = await request.json()
    url = (data.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="missing url")
    _state["target"] = url
    _save_target(url)
    log.info("target updated -> %s", url)
    return {"ok": True, "target": url}
