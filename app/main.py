import warnings
import logging
import sys

warnings.filterwarnings("ignore", category=FutureWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)

logger = logging.getLogger(__name__)
logger.info("Terminal logging initialized")
print("[startup] app.main imported and logging initialized", flush=True)

def terminal_boot_message():
    print("[startup] FastAPI app is starting", flush=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import endpoints, auth, websocket_endpoints
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(endpoints.router)
app.include_router(websocket_endpoints.router, tags=["WebSocket"])


@app.on_event("startup")
async def on_startup():
    terminal_boot_message()
    logger.info("FastAPI startup event fired")

@app.get("/")
async def root():
    return {
        "message": "Robust Architecture Generator API v2.0",
        "features": [
            "User authentication and authorization",
            "Project analysis and context extraction",
            "Dynamic clarification questions",
            "ReactFlow architecture diagrams",
            "Database schema diagrams",
            "Detailed text architecture documents",
        ],
        "available_icons": settings.AVAILABLE_ICONS,
        "protected_endpoints": [
            "/architecture/analyze",
            "/architecture/generate-diagram",
            "/architecture/generate-text-architecture",
            "/architecture/threads",
            "/architecture/conversations",
        ],
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.PROJECT_VERSION,
    }


@app.get("/icons")
async def get_available_icons():
    """Return list of available icons for frontend"""
    return {"icons": settings.AVAILABLE_ICONS}

