"""
VenueFlow API — FastAPI entry point.
Crowd-aware, accessibility-first stadium navigator — Google Cloud powered.
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from api.middleware.security import SecurityHeadersMiddleware, RateLimitHeaderMiddleware
from api.routes import route, zones, waittimes, alerts, assistant
from api.ws.manager import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}'
)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("VenueFlow starting — region=%s", os.getenv("REGION", "local"))
    yield
    logger.info("VenueFlow shutting down")


app = FastAPI(
    title="VenueFlow API",
    description="Crowd-aware, accessibility-first stadium navigator.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitHeaderMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Session-ID"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/health", tags=["ops"])
async def health():
    """Cloud Run liveness probe — must return 200 for deployment to succeed."""
    return {
        "status": "ok",
        "service": "venueflow",
        "version": "2.0.0",
        "region": os.getenv("REGION", "local"),
    }


app.include_router(zones.router,     prefix="/api", tags=["crowd"])
app.include_router(route.router,     prefix="/api", tags=["navigation"])
app.include_router(waittimes.router, prefix="/api", tags=["prediction"])
app.include_router(alerts.router,    prefix="/api", tags=["alerts"])
app.include_router(assistant.router, prefix="/api", tags=["ai"])
app.include_router(ws_router)

# Mount static files last — serves the PWA frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")
