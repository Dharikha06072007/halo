from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database.mongodb import db
from backend.routes.auth import get_current_user
from backend.services.gemini_service import create_interview_plan, decide_next_interview_step, evaluate_interview_answer, generate_final_feedback, generate_interview_question

router = APIRouter(prefix="/interview", tags=["interview"])


class InterviewStartRequest(BaseModel):
    analysis_id: str


class InterviewAnswerRequest(BaseModel):
    session_id: str
    question_id: str
    answer_submission_id: str
    transcript: str
class InterviewEndRequest(BaseModel):
    session_id: str


def object_id(value: str, label: str) -> ObjectId:
    try:
        return ObjectId(value)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {label}.") from exc


@router.post("/start")
async def start_interview(payload: InterviewStartRequest, current_user: dict = Depends(get_current_user)):
    analysis = db.resume_analyses.find_one({"_id": object_id(payload.analysis_id, "analysis id"), "user_id": current_user["_id"]})
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.get("status") == "PROCESSING":
        raise HTTPException(status_code=409, detail="Analysis is still being prepared.")
    if analysis.get("status") == "FAILED":
        raise HTTPException(status_code=409, detail="Analysis must be completed before starting an interview.")
    if analysis.get("status") != "COMPLETED" or not analysis.get("evidence_map", analysis.get("evidence")):
        raise HTTPException(status_code=409, detail="Analysis must be completed before starting an interview.")
    resume = db.resumes.find_one({"_id": analysis.get("resume_id"), "user_id": current_user["_id"]})
    job = db.job_descriptions.find_one({"_id": analysis.get("job_description_id"), "user_id": current_user["_id"]})
    if not resume:
        raise HTTPException(status_code=404, detail="Resume for this analysis was not found.")
    if not job:
        raise HTTPException(status_code=404, detail="Job description for this analysis was not found.")

    try:
        plan = create_interview_plan(analysis, resume, job)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="AI interviewer is temporarily unavailable. Please retry.") from exc
    topics = [topic.model_dump() for topic in plan.topics]
    if not topics:
        raise HTTPException(status_code=503, detail="AI interviewer could not prepare topics. Please retry.")
    session = {
        "user_id": current_user["_id"],
        "resume_id": analysis.get("resume_id"),
        "job_description_id": analysis.get("job_description_id"),
        "analysis_id": analysis["_id"],
        "status": "ACTIVE",
        "topics_planned": topics,
        "topics_completed": [],
        "current_topic": topics[0]["topic"],
        "current_question_id": None,
        "question_index": 0,
        "claims_made": [],
        "follow_up_counts": {},
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
        "created_at": datetime.now(timezone.utc),
    }
    result = db.interview_sessions.insert_one(session)
    first_topic = session["current_topic"]
    try:
        first_question = generate_interview_question(first_topic, resume, job, analysis).question
    except RuntimeError as exc:
        db.interview_sessions.delete_one({"_id": result.inserted_id})
        raise HTTPException(status_code=503, detail="AI interviewer is temporarily unavailable. Please retry.") from exc
    question_result = db.interview_questions.insert_one({
        "user_id": current_user["_id"],
        "session_id": result.inserted_id,
        "topic": first_topic,
        "question": first_question,
        "question_type": "MAIN",
        "follow_up_number": 0,
        "question_order": 1,
        "question_index": 0,
        "created_at": datetime.now(timezone.utc),
    })
    db.interview_sessions.update_one({"_id": result.inserted_id}, {"$set": {"current_question_id": question_result.inserted_id}})
    return {"session_id": str(result.inserted_id), "status": "ACTIVE", "job_title": analysis.get("job_title", "Target role"), "topics": topics, "question_number": 1, "first_question": {"id": str(question_result.inserted_id), "topic": first_topic, "question": first_question, "is_follow_up": False}}


@router.post("/answer")
async def submit_answer(payload: InterviewAnswerRequest, current_user: dict = Depends(get_current_user)):
    session = db.interview_sessions.find_one({"_id": object_id(payload.session_id, "session id"), "user_id": current_user["_id"]})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    question = db.interview_questions.find_one({"_id": object_id(payload.question_id, "question id"), "session_id": session["_id"], "user_id": current_user["_id"]})
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    existing = db.interview_answers.find_one({"answer_submission_id": payload.answer_submission_id})
    if existing:
        return {"status": "duplicate", "answer_id": str(existing["_id"]), "evaluation": existing.get("evaluation")}

    try:
        evaluation = evaluate_interview_answer(question.get("question", ""), payload.transcript, question.get("topic", ""))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="AI interviewer is temporarily unavailable. Please retry your answer.") from exc
    answer_doc = {
        "user_id": current_user["_id"],
        "session_id": session["_id"],
        "question_id": question["_id"],
        "answer_submission_id": payload.answer_submission_id,
        "transcript": payload.transcript,
        "question": question.get("question", ""),
        "evaluation": evaluation.model_dump() if hasattr(evaluation, "model_dump") else evaluation,
        "created_at": datetime.now(timezone.utc),
    }
    answer_result = db.interview_answers.insert_one(answer_doc)
    resume = db.resumes.find_one({"_id": session.get("resume_id"), "user_id": current_user["_id"]}) or {}
    job = db.job_descriptions.find_one({"_id": session.get("job_description_id"), "user_id": current_user["_id"]}) or {}
    analysis = db.resume_analyses.find_one({"_id": session.get("analysis_id"), "user_id": current_user["_id"]}) or {}
    topic_names = [item.get("topic", "") if isinstance(item, dict) else str(item) for item in session.get("topics_planned", [])]
    current_topic = question.get("topic", "")
    follow_count = session.get("follow_up_counts", {}).get(current_topic, 0)
    remaining = [topic for topic in topic_names if topic != current_topic and topic not in session.get("topics_completed", [])]
    try:
        next_step = decide_next_interview_step(question.get("question", ""), payload.transcript, current_topic, remaining, follow_count, resume, job, analysis)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="AI interviewer is temporarily unavailable. Please retry your answer.") from exc
    if next_step.action == "END_INTERVIEW" or not remaining and next_step.action != "ASK_FOLLOW_UP":
        return {"status": "saved", "answer_id": str(answer_result.inserted_id), "evaluation": answer_doc["evaluation"], "next_action": "END_INTERVIEW"}
    next_topic = current_topic if next_step.action == "ASK_FOLLOW_UP" else (next_step.topic or remaining[0])
    if next_step.action == "ASK_FOLLOW_UP":
        next_follow_count = follow_count + 1
        if next_follow_count > 2:
            next_topic = remaining[0] if remaining else current_topic
            next_follow_count = 0
    else:
        next_follow_count = 0
    try:
        next_question = next_step.question or generate_interview_question(next_topic, resume, job, analysis).question
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="AI interviewer is temporarily unavailable. Please retry your answer.") from exc
    question_order = int(session.get("question_index", 0)) + 2
    new_question = db.interview_questions.insert_one({
        "user_id": current_user["_id"], "session_id": session["_id"], "topic": next_topic,
        "question": next_question, "question_type": "FOLLOW_UP" if next_step.action == "ASK_FOLLOW_UP" else "MAIN",
        "follow_up_number": next_follow_count, "question_order": question_order, "created_at": datetime.now(timezone.utc),
    })
    completed_topics = list(dict.fromkeys(session.get("topics_completed", []) + [current_topic]))
    counts = dict(session.get("follow_up_counts", {})); counts[current_topic] = next_follow_count
    db.interview_sessions.update_one({"_id": session["_id"]}, {"$set": {"current_question_id": new_question.inserted_id, "current_topic": next_topic, "question_index": question_order - 1, "topics_completed": completed_topics, "follow_up_counts": counts}})
    return {"status": "saved", "answer_id": str(answer_result.inserted_id), "evaluation": answer_doc["evaluation"], "next_action": next_step.action, "next_question": {"id": str(new_question.inserted_id), "topic": next_topic, "question": next_question, "is_follow_up": next_step.action == "ASK_FOLLOW_UP"}}


@router.post("/end")
async def end_interview(payload: InterviewEndRequest, current_user: dict = Depends(get_current_user)):
    session = db.interview_sessions.find_one({"_id": object_id(payload.session_id, "session id"), "user_id": current_user["_id"]})
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
    session = db.interview_sessions.find_one({"_id": object_id(session_id, "session id"), "user_id": current_user["_id"]})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    question = db.interview_questions.find_one({"_id": session.get("current_question_id"), "session_id": session["_id"], "user_id": current_user["_id"]})
    return {
        "status": session.get("status", "ACTIVE"),
        "current_question": str(session.get("current_question_id")) if session.get("current_question_id") else None,
        "question_id": str(question["_id"]) if question else None,
        "question_number": session.get("question_index", 0) + 1,
        "question_text": question.get("question", "") if question else "",
        "question_topic": question.get("topic", "") if question else "",
        "question_index": session.get("question_index", 0),
        "topics_completed": session.get("topics_completed", []),
        "pending_answer_submission_id": None,
    }


@router.get("/{session_id}/report")
async def get_session_report(session_id: str, current_user: dict = Depends(get_current_user)):
    session = db.interview_sessions.find_one({"_id": object_id(session_id, "session id"), "user_id": current_user["_id"]})
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
    scored = [item["score"] for item in report if isinstance(item.get("score"), (int, float))]
    feedback = db.interview_feedback.find_one({"session_id": session["_id"], "user_id": current_user["_id"]}) or {}
    return {"status": session.get("status"), "overall_score": round(sum(scored) / (len(scored) * 10) * 100, 2) if scored else None, "strong_areas": feedback.get("strong_areas", []), "areas_to_improve": feedback.get("areas_to_improve", []), "overall_feedback": feedback.get("overall_feedback", ""), "report": report}
