from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database.mongodb import db
from backend.routes.auth import get_current_user
from backend.services.embedding_service import calculate_similarity

router = APIRouter(prefix="/match", tags=["match"])


class MatchRequest(BaseModel):
    resume_id: str
    job_description_id: str


@router.post("")
async def match_resume(request: MatchRequest, current_user: dict = Depends(get_current_user)):
    resume = db.resumes.find_one({"_id": __import__('bson').objectid.ObjectId(request.resume_id), "user_id": current_user["_id"]})
    job = db.job_descriptions.find_one({"_id": __import__('bson').objectid.ObjectId(request.job_description_id), "user_id": current_user["_id"]})
    if not resume or not job:
        raise HTTPException(status_code=404, detail="Resume or job description not found")

    parsed_resume = resume.get("parsed_data", {})
    parsed_job = job.get("parsed_data", {})

    required_skills = parsed_job.get("required_skills", [])
    resume_skills = parsed_resume.get("skills", [])
    matched = []
    partial = []
    not_demo = []
    evidence = []

    for skill in required_skills:
        match_score = 0.0
        for resume_skill in resume_skills:
            similarity = calculate_similarity(str(skill), str(resume_skill))
            match_score = max(match_score, similarity)
        status = "MATCHED" if match_score >= 0.75 else "PARTIAL" if match_score >= 0.45 else "NOT_DEMONSTRATED"
        if status == "MATCHED":
            matched.append(skill)
        elif status == "PARTIAL":
            partial.append(skill)
        else:
            not_demo.append(skill)
        evidence.append({
            "skill": skill,
            "status": status,
            "jd_requirement": skill,
            "resume_evidence": next((item for item in resume_skills if str(item).lower() in str(skill).lower()), "No clear evidence found in the resume."),
            "semantic_similarity": round(match_score, 4),
            "explanation": "Matched using semantic evidence and role requirements." if status == "MATCHED" else "Partial evidence found in the resume." if status == "PARTIAL" else "No clear evidence found in the resume.",
        })

    overall = round((len(matched) / max(len(required_skills), 1)) * 100, 2) if required_skills else 0.0
    analysis = {
        "user_id": current_user["_id"],
        "resume_id": resume["_id"],
        "job_description_id": job["_id"],
        "overall_match_score": overall,
        "matched_skills": matched,
        "partial_skills": partial,
        "not_demonstrated_skills": not_demo,
        "evidence": evidence,
        "created_at": datetime.now(timezone.utc),
    }
    result = db.resume_analyses.insert_one(analysis)
    return {"id": str(result.inserted_id), "overall_match_score": overall, "matched_skills": matched, "partial_skills": partial, "not_demonstrated_skills": not_demo, "evidence": evidence}
