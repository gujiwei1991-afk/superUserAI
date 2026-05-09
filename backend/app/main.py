import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.tasks import router as tasks_router
from app.api.webhooks import router as webhooks_router
from app.database import close_db, init_db
from app.gateway.wechat_gateway import router as wechat_router

# Make our `app.*` loggers visible alongside uvicorn's access log. Without this,
# logger.info() calls inside services/handlers stay silent under `--log-level info`.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
# Loggers that matter for the WeChat → bound-group → bridge pipeline.
for name in (
    "app.gateway.wechat_gateway",
    "app.services.message_handler",
    "app.services.group_message_router",
    "app.services.group_intent",
    "app.services.group_image_handler",
    "app.services.image_bridge_client",
    "app.services.repo_binding_service",
    "app.services.session_manager",
    "app.agents.pm_agent",
):
    logging.getLogger(name).setLevel(logging.INFO)

BASE_DIR = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(title="SuperUserAI Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = BASE_DIR / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(admin_router)
app.include_router(wechat_router)
app.include_router(tasks_router)
app.include_router(webhooks_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
