from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.database.mongodb import db
from backend.routes.auth import get_current_user
from backend.routes.match import MatchRequest, match_resume
from backend.services.gemini_service import generate_learning_path

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _public_analysis(item: dict) -> dict:
    resume = db.resumes.find_one({"_id": item.get("resume_id")}, {"file_name": 1}) if item.get("resume_id") else None
    job = db.job_descriptions.find_one({"_id": item.get("job_description_id")}, {"parsed_data": 1}) if item.get("job_description_id") else None
    evidence = item.get("evidence_map", item.get("evidence", []))
    recommendations = item.get("improvement_recommendations", [entry for entry in evidence if entry.get("status") != "MATCHED"][:5])
    result = {
        "id": str(item["_id"]),
        "status": item.get("status") or ("COMPLETED" if evidence else "INCOMPLETE"),
        "job_title": item.get("job_title") or (job or {}).get("parsed_data", {}).get("job_title", "Target role"),
        "resume_file_name": item.get("resume_file_name") or (resume or {}).get("file_name", "Resume"),
        "overall_match_score": item.get("overall_match_score") if item.get("status") or evidence else None,
        "matched_skills": item.get("matched_skills", []),
        "partial_skills": item.get("partial_skills", []),
        "not_demonstrated_skills": item.get("not_demonstrated_skills", []),
        "evidence_map": evidence,
        "improvement_recommendations": recommendations,
        "resume_improvements": item.get("resume_improvements", []),
        "created_at": item.get("created_at").isoformat() if item.get("created_at") else None,
    }
    if result["overall_match_score"] is None:
        del result["overall_match_score"]
    return result


@router.get("")
async def list_analyses(current_user: dict = Depends(get_current_user)):
    rows = list(db.resume_analyses.find({"user_id": current_user["_id"]}).sort("created_at", -1))
    return [_public_analysis(item) for item in rows]


@router.get("/{analysis_id}")
async def get_analysis(analysis_id: str, current_user: dict = Depends(get_current_user)):
    analysis = db.resume_analyses.find_one({"_id": __import__('bson').objectid.ObjectId(analysis_id), "user_id": current_user["_id"]})
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _public_analysis(analysis)


@router.post("/{analysis_id}/reprocess")
async def reprocess_analysis(analysis_id: str, current_user: dict = Depends(get_current_user)):
    analysis = db.resume_analyses.find_one({"_id": __import__('bson').objectid.ObjectId(analysis_id), "user_id": current_user["_id"]})
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return await match_resume(MatchRequest(
        resume_id=str(analysis["resume_id"]),
        job_description_id=str(analysis["job_description_id"]),
    ), current_user)


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
