from __future__ import annotations

import json
import logging
from typing import Any

import google.generativeai as genai
from pydantic import BaseModel, ValidationError

from backend.core.config import settings


genai.configure(api_key=settings.GEMINI_API_KEY)
logger = logging.getLogger("skillsync.gemini")


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


class InterviewTopic(BaseModel):
    topic: str
    reason: str = ""
    source: str = "RESUME"


class InterviewPlan(BaseModel):
    topics: list[InterviewTopic] = []


class InterviewQuestion(BaseModel):
    question: str


class InterviewStep(BaseModel):
    action: str
    topic: str = ""
    question: str = ""
    follow_up_number: int = 0


def _model():
    return genai.GenerativeModel(settings.GEMINI_MODEL)


def _safe_call(prompt: str, schema: type[BaseModel] | None = None, temperature: float = 0.2):
    try:
        result = _model().generate_content(
            prompt,
            generation_config={"temperature": temperature, "response_mime_type": "application/json"},
            request_options={"timeout": 30},
        )
        text = result.text.strip()
        if not text:
            raise ValueError("Empty Gemini response")
        data = json.loads(text)
        if schema is not None:
            return schema.model_validate(data)
        return data
    except Exception as exc:
        logger.exception("Gemini request failed: %s", type(exc).__name__)
        raise RuntimeError(f"Gemini request failed: {exc}") from exc


def extract_resume(raw_text: str):
    prompt = f"Extract resume data into strict JSON. Use only evidence in the resume. If missing, return empty arrays/empty strings. Respond as valid JSON only.\n\nRESUME:\n{raw_text[:20000]}"
    try:
        return _safe_call(prompt, ResumeExtraction)
    except RuntimeError:
        return _local_resume_extraction(raw_text)


def extract_job_description(raw_text: str):
    prompt = f"Extract job description data into strict JSON. Use only evidence in the job description. If missing, return empty arrays/empty strings. Respond as valid JSON only.\n\nJOB DESCRIPTION:\n{raw_text[:20000]}"
    try:
        return _safe_call(prompt, JobExtraction)
    except RuntimeError:
        return _local_job_extraction(raw_text)


_KNOWN_SKILLS = (
    "Python", "FastAPI", "Django", "Flask", "JavaScript", "TypeScript", "React", "Node.js",
    "MongoDB", "PostgreSQL", "SQL", "Docker", "Kubernetes", "AWS", "Azure", "GCP", "REST APIs",
    "GraphQL", "Git", "TensorFlow", "PyTorch", "Java", "C++", "C#", "Redis", "Linux",
)


def _detected_skills(raw_text: str) -> list[str]:
    lowered = raw_text.lower()
    return [skill for skill in _KNOWN_SKILLS if skill.lower() in lowered]


def _local_resume_extraction(raw_text: str) -> ResumeExtraction:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    skills = _detected_skills(raw_text)
    return ResumeExtraction(
        candidate_summary=lines[0] if lines else "",
        skills=skills,
        technologies=skills,
    )


def _local_job_extraction(raw_text: str) -> JobExtraction:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    skills = _detected_skills(raw_text)
    title = lines[0][:120] if lines else "Target role"
    return JobExtraction(job_title=title, required_skills=skills, technologies=skills)


def reason_about_evidence(*args, **kwargs):
    return {"status": "ok"}


def generate_learning_path(analysis: dict[str, Any], *args, **kwargs):
    priorities = []
    for skill in analysis.get("not_demonstrated_skills", []):
        priorities.append({
            "skill": str(skill),
            "priority": "HIGH",
            "why_learn": "This requirement was not clearly demonstrated in the resume.",
            "steps": [f"Review the core concepts of {skill}", f"Build a small practical project using {skill}"],
            "practice_task": f"Explain how you would apply {skill} in the target role.",
        })
    for skill in analysis.get("partial_skills", []):
        priorities.append({
            "skill": str(skill),
            "priority": "MEDIUM",
            "why_learn": "The resume contains partial evidence for this requirement.",
            "steps": [f"Strengthen your working knowledge of {skill}", f"Prepare one concrete example using {skill}"],
            "practice_task": f"Describe a project where {skill} improved the outcome.",
        })
    return {"learning_path": priorities}


def create_interview_plan(analysis: dict[str, Any], resume: dict[str, Any], job: dict[str, Any], *args, **kwargs):
    prompt = (
        "Create a structured interview plan as JSON with 8 to 10 topics. "
        "Each topic must have topic, reason, and source. Use only the supplied resume, job description, and analysis. "
        "Do not invent candidate experience or questions. Sources must be RESUME, JD, GAP, or BEHAVIORAL.\n\n"
        f"RESUME:\n{resume.get('raw_text', '')[:12000]}\n\n"
        f"JOB DESCRIPTION:\n{job.get('raw_text', '')[:12000]}\n\n"
        f"ANALYSIS:\n{json.dumps(analysis, default=str)[:12000]}"
    )
    raw_plan = _safe_call(prompt)
    if isinstance(raw_plan, list):
        raw_plan = {"topics": raw_plan}
    return InterviewPlan.model_validate(raw_plan)


def generate_interview_question(topic: str, resume: dict[str, Any], job: dict[str, Any], analysis: dict[str, Any], *args, **kwargs):
    prompt = (
        "Generate one personalized interview question as JSON with a question field. "
        "Ask only about the supplied resume, job description, analysis, and topic. Never assume experience not shown.\n\n"
        f"TOPIC: {topic}\nRESUME:\n{resume.get('raw_text', '')[:10000]}\n"
        f"JOB:\n{job.get('raw_text', '')[:10000]}\nANALYSIS:\n{json.dumps(analysis, default=str)[:10000]}"
    )
    return _safe_call(prompt, InterviewQuestion)


def decide_next_interview_step(question: str, answer: str, topic: str, remaining_topics: list[str], follow_up_number: int, resume: dict[str, Any], job: dict[str, Any], analysis: dict[str, Any]):
    prompt = (
        "Choose the next interview action as strict JSON. action must be ASK_FOLLOW_UP, NEXT_TOPIC, or END_INTERVIEW. "
        "Ask at most one follow-up per topic and never exceed follow_up_number 2. "
        "When asking a follow-up, write the question using only supplied evidence.\n\n"
        f"TOPIC: {topic}\nQUESTION: {question}\nANSWER: {answer}\nREMAINING TOPICS: {remaining_topics}\n"
        f"RESUME:\n{resume.get('raw_text', '')[:8000]}\nJOB:\n{job.get('raw_text', '')[:8000]}\nANALYSIS:\n{json.dumps(analysis, default=str)[:8000]}"
    )
    return _safe_call(prompt, InterviewStep)


def evaluate_interview_answer(question: str, answer: str, topic: str = ""):
    prompt = (
        "Evaluate the candidate answer using strict JSON with fields: score (0-10), feedback, good_point, improvement. "
        "Do not reward length alone. Return only JSON.\n\n"
        f"TOPIC: {topic}\nQUESTION: {question}\nANSWER: {answer}"
    )
    return _safe_call(prompt, AnswerEvaluation)


def generate_final_feedback(session: dict[str, Any], *args, **kwargs):
    return {
        "strong_areas": session.get("topics_completed", [])[:3],
        "areas_to_improve": session.get("topics_planned", [])[len(session.get("topics_completed", [])):][:3],
        "overall_feedback": "Review each answer and turn the strongest examples into concise stories with clear outcomes.",
    }
