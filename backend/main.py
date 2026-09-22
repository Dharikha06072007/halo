from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError

from backend.core.config import settings, require_required_settings
from backend.database.mongodb import ensure_indexes, ping_db
from backend.routes.auth import router as auth_router
from backend.routes.resume import router as resume_router
from backend.routes.job import router as job_router
from backend.routes.match import router as match_router
from backend.routes.analysis import router as analysis_router
from backend.routes.interview import router as interview_router
from backend.routes.health import router as health_router


logger = logging.getLogger("skillsync")


@asynccontextmanager
async def lifespan(app: FastAPI):
    require_required_settings()
    try:
        ping_db()
        ensure_indexes()
        app.state.db_connected = True
    except PyMongoError as exc:
        app.state.db_connected = False
        logger.exception("MongoDB connection failed during startup: %s", exc)
    except Exception as exc:
        app.state.db_connected = False
        logger.exception("Startup configuration error: %s", exc)
    yield


app = FastAPI(title="SkillSync AI", version="1.0.0", lifespan=lifespan)

allowed_origins = {
    settings.FRONTEND_URL,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(resume_router, prefix="/api")
app.include_router(job_router, prefix="/api")
app.include_router(match_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(interview_router, prefix="/api")
app.include_router(health_router, prefix="/api")


@app.get("/")
async def root():
    return {"message": "SkillSync AI API"}
