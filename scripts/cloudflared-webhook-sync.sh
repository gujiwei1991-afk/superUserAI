#!/bin/bash
# 启动 cloudflared 快速隧道，抓取新分配的公网 URL，
# 并自动把 GitHub webhook 的 Payload URL 更新成它。
# 这样即使隧道进程重启拿到新 URL，webhook 也会自愈，无需人工干预。
#
# 由 launchd (com.superuserai.cloudflared) 调用，作为长驻进程。
set -uo pipefail

CLOUDFLARED=/opt/homebrew/bin/cloudflared
BACKEND_ENV=/Users/gujiwei/python/superUserAI/backend/.env
REPO="gujiwei1991-afk/oaSys"
HOOK_ID=634610113
LOCAL_URL="http://localhost:8000"
OUT=$(mktemp /tmp/cloudflared-out.XXXXXX)

# 启动隧道（http2 协议，绕过被拦的 QUIC/UDP）
"$CLOUDFLARED" tunnel --url "$LOCAL_URL" --protocol http2 >"$OUT" 2>&1 &
CF_PID=$!

# launchd 卸载/停止时，确保连 cloudflared 子进程一起收掉
trap 'kill "$CF_PID" 2>/dev/null; rm -f "$OUT"' TERM EXIT

# 轮询抓取分配的 *.trycloudflare.com URL（最多等 40 秒）
PUBLIC_URL=""
for _ in $(seq 1 40); do
    PUBLIC_URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$OUT" | head -1)
    [ -n "$PUBLIC_URL" ] && break
    sleep 1
done

if [ -n "$PUBLIC_URL" ]; then
    echo "[sync] tunnel up: $PUBLIC_URL"
    TOKEN=$(grep '^github_token=' "$BACKEND_ENV" | cut -d= -f2-)
    SECRET=$(grep '^github_webhook_secret=' "$BACKEND_ENV" | cut -d= -f2-)
    # 更新 webhook 的 Payload URL（含 secret，避免被清空）
    code=$(curl -s -o /tmp/webhook-sync-resp.json -w "%{http_code}" \
        -X PATCH \
        -H "Authorization: Bearer $TOKEN" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/$REPO/hooks/$HOOK_ID" \
        -d "{\"config\":{\"url\":\"$PUBLIC_URL/api/webhooks/github\",\"content_type\":\"json\",\"secret\":\"$SECRET\",\"insecure_ssl\":\"0\"}}")
    echo "[sync] github webhook update HTTP $code"
else
    echo "[sync] WARNING: 未能在超时内抓到隧道 URL，webhook 未更新"
fi

# 阻塞直到 cloudflared 退出；退出后 launchd 会重启本脚本 → 重新建隧道并自愈 webhook
wait "$CF_PID"
