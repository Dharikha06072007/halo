from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import fitz
from docx import Document
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.database.mongodb import db
from backend.routes.auth import get_current_user
from backend.services.gemini_service import extract_resume

router = APIRouter(prefix="/resume", tags=["resume"])
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/upload")
async def upload_resume(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required.")

    extension = (file.filename.split(".")[-1] or "").lower()
    if extension not in {"pdf", "docx"}:
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload PDF or DOCX.")

    content = await file.read()
    if not content or len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File is too large. Max size is 10MB.")

    try:
        text = extract_resume_text(content, extension)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not extract text from the uploaded file.") from exc

    if not text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in the uploaded file.")

    parsed = extract_resume(text)
    safe_name = f"resume_{current_user['_id']}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{file.filename}"
    save_path = UPLOAD_DIR / safe_name.replace("/", "_").replace("\\", "_")
    save_path.write_bytes(content)

    result = db.resumes.insert_one({
        "user_id": current_user["_id"],
        "file_name": file.filename,
        "file_type": extension,
        "raw_text": text,
        "parsed_data": parsed.model_dump() if hasattr(parsed, "model_dump") else parsed,
        "created_at": datetime.now(timezone.utc),
    })

    return {
        "id": str(result.inserted_id),
        "file_name": file.filename,
        "file_type": extension,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("")
async def list_resumes(current_user: dict = Depends(get_current_user)):
    rows = list(db.resumes.find({"user_id": current_user["_id"]}).sort("created_at", -1))
    return [{
        "id": str(item["_id"]),
        "file_name": item.get("file_name"),
        "file_type": item.get("file_type"),
        "created_at": item["created_at"].isoformat(),
    } for item in rows]


def extract_resume_text(content: bytes, extension: str) -> str:
    if extension == "pdf":
        with fitz.open(stream=content, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc)

    if extension == "docx":
        import io

        document = Document(io.BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())

    raise ValueError("Unsupported file type.")
