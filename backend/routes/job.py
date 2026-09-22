from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database.mongodb import db
from backend.routes.auth import get_current_user
from backend.services.gemini_service import extract_job_description

router = APIRouter(prefix="/job", tags=["job"])


class JobAnalyzeRequest(BaseModel):
    job_description: str


@router.post("/analyze")
async def analyze_job(payload: JobAnalyzeRequest, current_user: dict = Depends(get_current_user)):
    if not payload.job_description or not payload.job_description.strip():
        raise HTTPException(status_code=400, detail="Job description is required.")

    try:
        parsed = extract_job_description(payload.job_description)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Job description AI analysis is temporarily unavailable. Please try again shortly.") from exc
    document = {
        "user_id": current_user["_id"],
        "raw_text": payload.job_description,
        "parsed_data": parsed.model_dump() if hasattr(parsed, "model_dump") else parsed,
        "created_at": datetime.now(timezone.utc),
    }
    result = db.job_descriptions.insert_one(document)
    return {
        "id": str(result.inserted_id),
        "job_title": parsed.job_title if hasattr(parsed, "job_title") else "",
        "required_skills": parsed.required_skills if hasattr(parsed, "required_skills") else [],
        "preferred_skills": parsed.preferred_skills if hasattr(parsed, "preferred_skills") else [],
    }
