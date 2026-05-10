# Staging 服务器一次性配置指南

> 给"自管 staging 服务器 + 公网 IP + 域名"场景准备的步骤。
> 完成这些之后，superUserAI 后端就能 SSH 上来自动部署 PR 到 staging。

## 前置

- 一台 Linux 服务器，有公网 IP，可 22 端口入站
- 一个域名 `your-domain.com`，DNS 管理权限
- 你的 superUserAI backend 运行机器（`backend-host`）

## 1. 服务器侧：装基础软件 + 建 deploy 用户

```bash
# 装 docker
curl -fsSL https://get.docker.com | sudo sh

# 装 docker compose plugin（Ubuntu/Debian）
sudo apt install docker-compose-plugin

# 装 nginx + certbot
sudo apt install nginx certbot python3-certbot-nginx

# 建 deploy 用户
sudo useradd -m -s /bin/bash deploy
sudo usermod -aG docker deploy
```

## 2. backend 机器：生成 SSH key

```bash
sudo mkdir -p /etc/superuserai
sudo ssh-keygen -t ed25519 -f /etc/superuserai/staging_id_ed25519 -N ""
sudo chown $(id -u):$(id -g) /etc/superuserai/staging_id_ed25519
sudo chmod 600 /etc/superuserai/staging_id_ed25519
```

把公钥（`/etc/superuserai/staging_id_ed25519.pub`）内容贴到 staging 服务器上 `deploy` 用户的 `~/.ssh/authorized_keys`：

```bash
# 在 staging 服务器上
sudo -iu deploy
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "<贴入公钥内容>" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
exit
```

测试 backend 能不能免密 SSH 上来：

```bash
# 在 backend 机器上
ssh -i /etc/superuserai/staging_id_ed25519 deploy@<staging-server-ip> "echo ok"
```
应该输出 `ok`，无密码提示。

## 3. staging 服务器：给 deploy 用户配 GitHub 拉取权限

需要 staging 服务器能 `git fetch` 你的 GitHub repo。最安全方案是给每个 repo 加一个 read-only deploy key：

```bash
# 在 staging 服务器上，作为 deploy 用户
sudo -iu deploy
ssh-keygen -t ed25519 -f ~/.ssh/<repo-name>_ed25519 -N ""
cat ~/.ssh/<repo-name>_ed25519.pub
```

把这个公钥贴到 GitHub repo Settings → Deploy keys → Add deploy key（**不勾** "Allow write access"）。

然后配 SSH alias：

```bash
# ~/.ssh/config
Host github-<repo-name>
  HostName github.com
  User git
  IdentityFile ~/.ssh/<repo-name>_ed25519
  IdentitiesOnly yes
```

## 4. staging 服务器：第一次 git clone

```bash
sudo -iu deploy
sudo mkdir -p /srv/staging && sudo chown deploy:deploy /srv/staging
cd /srv/staging
git clone github-<repo-name>:<owner>/<repo>.git <repo-name>
```

之后 superUserAI 就只 `git fetch` + `git checkout`，不再 clone。

## 5. DNS：把 staging 子域名指向服务器

到你 DNS 管理面板，加一条 A 记录：
```
staging.your-domain.com  →  <staging-server-public-ip>
```

等 DNS 生效（通常 1~10 分钟），可用 `dig staging.your-domain.com` 验证。

## 6. nginx 反向代理 + Let's Encrypt 证书

假设你的 docker-compose.staging.yml 把 app 暴露到 `127.0.0.1:8080`。

写 `/etc/nginx/sites-available/staging.your-domain.com`：

```nginx
server {
    server_name staging.your-domain.com;
    listen 80;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

启用 + 申请证书：

```bash
sudo ln -s /etc/nginx/sites-available/staging.your-domain.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d staging.your-domain.com
```

certbot 会自动改 nginx 配启用 HTTPS + 配 80→443 跳转 + 写 cron 自动续证。

## 7. 项目侧：写 docker-compose.staging.yml

在你的 GitHub repo 根目录加一个 `docker-compose.staging.yml`，最小示例：

```yaml
services:
  app:
    build: .
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      - DATABASE_URL=postgres://user:pass@postgres:5432/staging
    depends_on:
      - postgres

  postgres:
    image: postgres:16
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=staging
    volumes:
      - staging_pg_data:/var/lib/postgresql/data

volumes:
  staging_pg_data:
```

要点：
- **app 端口绑 `127.0.0.1`**（让 nginx 反代来流量；不暴露 0.0.0.0 防绕过 TLS）
- DB / 上传文件 / 缓存 用 named volume 持久化
- 别在 staging 用生产数据，README 提示客户

## 8. backend 配置

backend 的 `.env` 里设：

```
staging_ssh_key_path=/etc/superuserai/staging_id_ed25519
staging_ssh_user_default=deploy
staging_deploy_timeout_sec=600
staging_log_tail_lines=200
```

到 superUserAI admin 后台，进入 Project 详情页，"Staging 部署配置" 这一栏填：
- Staging URL: `https://staging.your-domain.com`
- SSH 目标: `deploy@<staging-server-ip>`
- 服务器上的部署目录: `/srv/staging/<repo-name>`
- Docker Compose 文件名: `docker-compose.staging.yml`

## 9. 验证

让 dev-agent 跑一个简单 issue → 提 PR → 看 backend 日志：

```bash
journalctl -u superuserai-backend -f --since "2 minutes ago" | grep staging
```

应该看到：
- `staging deploy ... starting`
- 远端 docker compose 输出
- `staging deploy ... success`

然后企微 creator 应该收到一条文本 + 链接。
