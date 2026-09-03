"""
main.py — FastAPI application entry point.
Mounts all routers, configures CORS, and starts Uvicorn.
"""
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from config import settings
from api.routes import router

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("contractguard")

# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="ContractGuard API",
    description="Autonomous AI agent for smart contract fraud risk investigation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ────────────────────────────────────────────────────────────────
app.include_router(router, prefix="")

# ── Serve frontend static files ───────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

# ── Startup / shutdown events ─────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    logger.info("ContractGuard API starting up...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Gemini model: {settings.gemini_model}")
    logger.info(f"Chain provider: {settings.web3_provider_url[:40]}...")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("ContractGuard API shutting down.")


# ── Dev runner ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level="info",
    )
