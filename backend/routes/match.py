from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database.mongodb import db
from backend.routes.auth import get_current_user
from backend.services.embedding_service import calculate_similarity

router = APIRouter(prefix="/match", tags=["match"])
_semantic_disabled_until = 0.0


class MatchRequest(BaseModel):
    resume_id: str
    job_description_id: str


def _lexical_similarity(first: str, second: str) -> float:
    first_words = {word.lower() for word in first.replace("/", " ").split() if len(word) > 2}
    second_words = {word.lower() for word in second.replace("/", " ").split() if len(word) > 2}
    if not first_words or not second_words:
        return 0.0
    return len(first_words & second_words) / len(first_words | second_words)


def _similarity(first: str, second: str) -> float:
    global _semantic_disabled_until
    if time.monotonic() < _semantic_disabled_until:
        return _lexical_similarity(first, second)
    try:
        return calculate_similarity(first, second)
    except Exception:
        _semantic_disabled_until = time.monotonic() + 60
        return _lexical_similarity(first, second)


def _evidence_candidates(parsed_resume: dict, raw_resume: str) -> list[str]:
    candidates = list(parsed_resume.get("skills", [])) + list(parsed_resume.get("technologies", []))
    for group in ("projects", "experience"):
        for item in parsed_resume.get(group, []):
            if isinstance(item, dict):
                candidates.extend(str(value) for value in item.values() if value)
            else:
                candidates.append(str(item))
    if parsed_resume.get("candidate_summary"):
        candidates.append(str(parsed_resume["candidate_summary"]))
    candidates.extend(line.strip() for line in raw_resume.splitlines() if line.strip())
    return list(dict.fromkeys(candidates)) or ["No clear evidence found in the resume."]


@router.post("")
async def match_resume(request: MatchRequest, current_user: dict = Depends(get_current_user)):
    resume = db.resumes.find_one({"_id": __import__('bson').objectid.ObjectId(request.resume_id), "user_id": current_user["_id"]})
    job = db.job_descriptions.find_one({"_id": __import__('bson').objectid.ObjectId(request.job_description_id), "user_id": current_user["_id"]})
    if not resume or not job:
        raise HTTPException(status_code=404, detail="Resume or job description not found")

    parsed_resume = resume.get("parsed_data", {})
    parsed_job = job.get("parsed_data", {})

    required_skills = list(dict.fromkeys(parsed_job.get("required_skills", []) + parsed_job.get("technologies", [])))
    evidence_candidates = _evidence_candidates(parsed_resume, resume.get("raw_text", ""))
    matched = []
    partial = []
    not_demo = []
    evidence = []

    for skill in required_skills:
        match_score = 0.0
        best_evidence = "No clear evidence found in the resume."
        ranked_evidence = sorted(
            evidence_candidates,
            key=lambda evidence: _lexical_similarity(str(skill), str(evidence)),
            reverse=True,
        )[:1]
        for resume_evidence in ranked_evidence:
            similarity = _similarity(str(skill), str(resume_evidence))
            if similarity > match_score:
                match_score = similarity
                best_evidence = str(resume_evidence)
        status = "MATCHED" if match_score >= 0.75 else "PARTIAL" if match_score >= 0.45 else "NOT_DEMONSTRATED"
        if status == "MATCHED":
            matched.append(skill)
        elif status == "PARTIAL":
            partial.append(skill)
        else:
            not_demo.append(skill)
        missing = ""
        improvement = ""
        if status == "PARTIAL":
            missing = "The resume shows related evidence but not enough detail to confirm the full requirement."
            improvement = f"If applicable, describe a real project where you used {skill} and the outcome."
        elif status == "NOT_DEMONSTRATED":
            missing = "No clear evidence found in the resume."
            improvement = f"If you have used {skill}, add the specific project, responsibility, or result where it was applied."
        evidence.append({
            "skill": skill,
            "status": status,
            "jd_requirement": skill,
            "resume_evidence": best_evidence,
            "semantic_similarity": round(match_score, 4),
            "explanation": "The resume contains strong evidence aligned with this requirement." if status == "MATCHED" else "The resume contains related evidence, but the requirement is not fully demonstrated." if status == "PARTIAL" else "This requirement is not clearly demonstrated in the resume.",
            "missing_evidence": missing,
            "improvement": improvement,
        })

    overall = round(((len(matched) + (len(partial) * 0.5)) / max(len(required_skills), 1)) * 100, 2) if required_skills else 0.0
    resume_improvements = [
        "Add measurable outcomes to relevant project and experience descriptions where the resume currently lists responsibilities only.",
        "Clarify the resume evidence for the highest-priority requirements identified in this analysis.",
    ] if evidence else []
    recommendations = [item for item in evidence if item["status"] != "MATCHED"][:5]
    analysis = {
        "user_id": current_user["_id"],
        "resume_id": resume["_id"],
        "job_description_id": job["_id"],
        "job_title": parsed_job.get("job_title", "Target role"),
        "resume_file_name": resume.get("file_name", "Resume"),
        "overall_match_score": overall,
        "matched_skills": matched,
        "partial_skills": partial,
        "not_demonstrated_skills": not_demo,
        "evidence": evidence,
        "evidence_map": evidence,
        "improvement_recommendations": recommendations,
        "resume_improvements": resume_improvements,
        "status": "COMPLETED",
        "created_at": datetime.now(timezone.utc),
    }
    result = db.resume_analyses.insert_one(analysis)
    return {"id": str(result.inserted_id), "status": "COMPLETED", "job_title": analysis["job_title"], "overall_match_score": overall, "matched_skills": matched, "partial_skills": partial, "not_demonstrated_skills": not_demo, "evidence_map": evidence, "improvement_recommendations": recommendations, "resume_improvements": resume_improvements}
