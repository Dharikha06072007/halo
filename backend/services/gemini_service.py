from __future__ import annotations

import json
from typing import Any

import google.generativeai as genai
from pydantic import BaseModel, ValidationError

from backend.core.config import settings


genai.configure(api_key=settings.GEMINI_API_KEY)


class ResumeExtraction(BaseModel):
    candidate_summary: str = ""
    skills: list[str] = []
    technologies: list[str] = []
    projects: list[dict[str, Any]] = []
    experience: list[dict[str, Any]] = []
    education: list[dict[str, Any]] = []
    certifications: list[str] = []


class JobExtraction(BaseModel):
    job_title: str = ""
    required_skills: list[str] = []
    preferred_skills: list[str] = []
    technologies: list[str] = []
    responsibilities: list[str] = []
    experience_requirements: list[str] = []
    education_requirements: list[str] = []


class AnswerEvaluation(BaseModel):
    score: int = 0
    feedback: str = ""
    good_point: str = ""
    improvement: str = ""


class LearningPathItem(BaseModel):
    skill: str = ""
    priority: str = "MEDIUM"
    why_learn: str = ""
    steps: list[str] = []
    practice_task: str = ""


def _model():
    return genai.GenerativeModel(settings.GEMINI_MODEL)


def _safe_call(prompt: str, schema: type[BaseModel] | None = None, temperature: float = 0.2):
    try:
        result = _model().generate_content(prompt, generation_config={"temperature": temperature, "response_mime_type": "application/json"})
        text = result.text.strip()
        if not text:
            raise ValueError("Empty Gemini response")
        data = json.loads(text)
        if schema is not None:
            return schema.model_validate(data)
        return data
    except Exception as exc:
        raise RuntimeError(f"Gemini request failed: {exc}") from exc


def extract_resume(raw_text: str):
    prompt = f"Extract resume data into strict JSON. Use only evidence in the resume. If missing, return empty arrays/empty strings. Respond as valid JSON only.\n\nRESUME:\n{raw_text[:20000]}"
    return _safe_call(prompt, ResumeExtraction)


def extract_job_description(raw_text: str):
    prompt = f"Extract job description data into strict JSON. Use only evidence in the job description. If missing, return empty arrays/empty strings. Respond as valid JSON only.\n\nJOB DESCRIPTION:\n{raw_text[:20000]}"
    return _safe_call(prompt, JobExtraction)


def reason_about_evidence(*args, **kwargs):
    return {"status": "ok"}


def generate_learning_path(*args, **kwargs):
    return {"learning_path": []}


def create_interview_plan(*args, **kwargs):
    return {"topics": []}


def generate_interview_question(*args, **kwargs):
    return {"question": ""}


def evaluate_interview_answer(question: str, answer: str, topic: str = ""):
    prompt = (
        "Evaluate the candidate answer using strict JSON with fields: score (0-10), feedback, good_point, improvement. "
        "Do not reward length alone. Return only JSON.\n\n"
        f"TOPIC: {topic}\nQUESTION: {question}\nANSWER: {answer}"
    )
    return _safe_call(prompt, AnswerEvaluation)


def generate_final_feedback(*args, **kwargs):
    return {"strong_areas": [], "areas_to_improve": [], "overall_feedback": ""}
