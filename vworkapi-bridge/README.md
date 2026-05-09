# vworkapi-bridge

A small FastAPI service that runs alongside vworkApi on the Windows host.
Exposes one endpoint `POST /fetch-image` that:

1. Calls local vworkApi (`type=9001`) to download an image to a temp file.
2. Uploads the file to Qiniu via the SDK.
3. Returns the public CDN URL to the caller.

## Install (Windows)

```bat
:: Python 3.10+ required
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env
notepad .env   :: fill in QINIU_* and IMAGE_BRIDGE_TOKEN
```

## Run

```bat
uvicorn app.main:app --host 0.0.0.0 --port 9100
```

For long-running deployment, register as a Windows service via `nssm`:

```bat
nssm install vworkapi-bridge "C:\path\to\.venv\Scripts\uvicorn.exe" ^
  "app.main:app --host 0.0.0.0 --port 9100"
nssm start vworkapi-bridge
```

## Auth

Every request must include `X-Bridge-Token: <IMAGE_BRIDGE_TOKEN>` matching the
.env value.

## Endpoints

- `GET  /healthz` — health check
- `POST /fetch-image` — see backend `image_bridge_client.py` for the request shape
