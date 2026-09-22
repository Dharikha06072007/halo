from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database.mongodb import db
from backend.routes.auth import get_current_user
from backend.services.gemini_service import create_interview_plan, evaluate_interview_answer, generate_final_feedback

router = APIRouter(prefix="/interview", tags=["interview"])


class InterviewStartRequest(BaseModel):
    analysis_id: str


class InterviewAnswerRequest(BaseModel):
    session_id: str
    question_id: str
    answer_submission_id: str
    transcript: str


@router.post("/start")
async def start_interview(payload: InterviewStartRequest, current_user: dict = Depends(get_current_user)):
    analysis = db.resume_analyses.find_one({"_id": __import__('bson').objectid.ObjectId(payload.analysis_id), "user_id": current_user["_id"]})
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    plan = create_interview_plan(analysis)
    session = {
        "user_id": current_user["_id"],
        "resume_id": analysis.get("resume_id"),
        "job_description_id": analysis.get("job_description_id"),
        "analysis_id": analysis["_id"],
        "status": "ACTIVE",
        "topics_planned": plan.get("topics", []),
        "topics_completed": [],
        "current_topic": plan.get("topics", [None])[0] if plan.get("topics") else "",
        "current_question_id": None,
        "question_index": 0,
        "claims_made": [],
        "follow_up_counts": {},
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
        "created_at": datetime.now(timezone.utc),
    }
    result = db.interview_sessions.insert_one(session)
    return {"session_id": str(result.inserted_id), "topics": plan.get("topics", [])}


@router.post("/answer")
async def submit_answer(payload: InterviewAnswerRequest, current_user: dict = Depends(get_current_user)):
    session = db.interview_sessions.find_one({"_id": __import__('bson').objectid.ObjectId(payload.session_id), "user_id": current_user["_id"]})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    question = db.interview_questions.find_one({"_id": __import__('bson').objectid.ObjectId(payload.question_id), "session_id": session["_id"], "user_id": current_user["_id"]})
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    existing = db.interview_answers.find_one({"answer_submission_id": payload.answer_submission_id})
    if existing:
        return {"status": "duplicate", "answer_id": str(existing["_id"]), "evaluation": existing.get("evaluation")}

    evaluation = evaluate_interview_answer(question.get("question", ""), payload.transcript, question.get("topic", ""))
    answer_doc = {
        "user_id": current_user["_id"],
        "session_id": session["_id"],
        "question_id": question["_id"],
        "answer_submission_id": payload.answer_submission_id,
        "transcript": payload.transcript,
        "evaluation": evaluation.model_dump() if hasattr(evaluation, "model_dump") else evaluation,
        "created_at": datetime.now(timezone.utc),
    }
    answer_result = db.interview_answers.insert_one(answer_doc)
    return {"status": "saved", "answer_id": str(answer_result.inserted_id), "evaluation": answer_doc["evaluation"]}


@router.post("/end")
async def end_interview(session_id: str, current_user: dict = Depends(get_current_user)):
    session = db.interview_sessions.find_one({"_id": __import__('bson').objectid.ObjectId(session_id), "user_id": current_user["_id"]})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.interview_sessions.update_one({"_id": session["_id"]}, {"$set": {"status": "COMPLETED", "completed_at": datetime.now(timezone.utc)}})
    final = generate_final_feedback(session)
    db.interview_feedback.insert_one({
        "user_id": current_user["_id"],
        "session_id": session["_id"],
        "strong_areas": final.get("strong_areas", []),
        "areas_to_improve": final.get("areas_to_improve", []),
        "question_feedback": [],
        "skill_recommendations": [],
        "learning_suggestions": [],
        "overall_feedback": final.get("overall_feedback", ""),
        "created_at": datetime.now(timezone.utc),
    })
    return {"status": "completed"}


@router.get("/{session_id}/state")
async def get_session_state(session_id: str, current_user: dict = Depends(get_current_user)):
    session = db.interview_sessions.find_one({"_id": __import__('bson').objectid.ObjectId(session_id), "user_id": current_user["_id"]})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "status": session.get("status", "ACTIVE"),
        "current_question": session.get("current_question_id"),
        "question_index": session.get("question_index", 0),
        "topics_completed": session.get("topics_completed", []),
        "pending_answer_submission_id": None,
    }


@router.get("/{session_id}/report")
async def get_session_report(session_id: str, current_user: dict = Depends(get_current_user)):
    session = db.interview_sessions.find_one({"_id": __import__('bson').objectid.ObjectId(session_id), "user_id": current_user["_id"]})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    answers = list(db.interview_answers.find({"session_id": session["_id"], "user_id": current_user["_id"]}))
    report = []
    for idx, answer in enumerate(answers, start=1):
        evaluation = answer.get("evaluation", {})
        report.append({
            "question_number": idx,
            "question": answer.get("question", ""),
            "answer": answer.get("transcript", ""),
            "score": evaluation.get("score", 0),
            "feedback": evaluation.get("feedback", ""),
            "good_point": evaluation.get("good_point", ""),
            "improvement": evaluation.get("improvement", ""),
            "is_follow_up": False,
        })
    return {"report": report}
