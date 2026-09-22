from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.database.mongodb import db
from backend.routes.auth import get_current_user
from backend.services.gemini_service import generate_learning_path

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("")
async def list_analyses(current_user: dict = Depends(get_current_user)):
    rows = list(db.resume_analyses.find({"user_id": current_user["_id"]}).sort("created_at", -1))
    return [{
        "id": str(item["_id"]),
        "overall_match_score": item.get("overall_match_score", 0),
        "matched_skills": item.get("matched_skills", []),
        "partial_skills": item.get("partial_skills", []),
        "not_demonstrated_skills": item.get("not_demonstrated_skills", []),
        "created_at": item["created_at"].isoformat(),
    } for item in rows]


@router.get("/{analysis_id}")
async def get_analysis(analysis_id: str, current_user: dict = Depends(get_current_user)):
    analysis = db.resume_analyses.find_one({"_id": __import__('bson').objectid.ObjectId(analysis_id), "user_id": current_user["_id"]})
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"id": str(analysis["_id"]), **{k: v for k, v in analysis.items() if k != "_id"}}


@router.get("/{analysis_id}/learning-path")
async def get_learning_path(analysis_id: str, current_user: dict = Depends(get_current_user)):
    analysis = db.resume_analyses.find_one({"_id": __import__('bson').objectid.ObjectId(analysis_id), "user_id": current_user["_id"]})
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    path = generate_learning_path(analysis)
    document = {
        "user_id": current_user["_id"],
        "analysis_id": __import__('bson').objectid.ObjectId(analysis_id),
        "skill_priorities": path.get("learning_path", []),
        "created_at": datetime.now(timezone.utc),
    }
    result = db.learning_paths.insert_one(document)
    return {"id": str(result.inserted_id), "skill_priorities": document["skill_priorities"]}
