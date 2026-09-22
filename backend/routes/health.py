from __future__ import annotations

from fastapi import APIRouter
from pymongo.errors import PyMongoError

from backend.core.config import settings
from backend.database.mongodb import ping_db

router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    db_status = "connected"
    gemini_status = "configured" if settings.GEMINI_API_KEY else "missing"
    hf_status = "configured" if settings.HF_TOKEN else "missing"

    try:
        ping_db()
    except (PyMongoError, RuntimeError):
        db_status = "unavailable"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "database": db_status,
        "gemini": gemini_status,
        "huggingface": hf_status,
    }
