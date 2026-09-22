from __future__ import annotations

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from backend.core.config import settings


client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
db = client[settings.MONGODB_DB]


def ping_db() -> None:
    if not settings.MONGODB_URI:
        raise RuntimeError("MONGODB_URI is not configured.")
    client.admin.command("ping")


def ensure_indexes() -> None:
    db.users.create_index("email", unique=True)
    db.interview_answers.create_index("answer_submission_id", unique=True)
    for collection_name, field_names in {
        "resumes": ["user_id", "created_at"],
        "job_descriptions": ["user_id", "created_at"],
        "resume_analyses": ["user_id", "resume_id", "job_description_id", "created_at"],
        "learning_paths": ["user_id", "analysis_id", "created_at"],
        "interview_sessions": ["user_id", "analysis_id", "created_at"],
        "interview_questions": ["user_id", "session_id", "created_at"],
        "interview_answers": ["user_id", "session_id", "question_id", "created_at"],
        "interview_feedback": ["user_id", "session_id", "created_at"],
    }.items():
        collection = db[collection_name]
        for field in field_names:
            collection.create_index(field)


def get_db():
    return db
