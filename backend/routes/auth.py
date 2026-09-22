from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from pymongo.errors import PyMongoError

from backend.core.config import settings
from backend.database.mongodb import db
from backend.utils.objectid import to_object_id

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def database_unavailable(exc: PyMongoError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication service is temporarily unavailable because the database cannot be reached.",
    )


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPayload(BaseModel):
    sub: str
    exp: int


class UserOut(BaseModel):
    id: str
    name: str
    email: str


@router.post("/register")
async def register(payload: RegisterRequest):
    try:
        existing = db.users.find_one({"email": payload.email.lower()})
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        user_doc = {
            "name": payload.name.strip(),
            "email": payload.email.lower(),
            "password_hash": pwd_context.hash(payload.password),
            "created_at": datetime.now(timezone.utc),
        }
        result = db.users.insert_one(user_doc)
        created = db.users.find_one({"_id": result.inserted_id})
    except PyMongoError as exc:
        raise database_unavailable(exc) from exc

    if created is None:
        raise HTTPException(status_code=500, detail="Could not create user")
    created.pop("password_hash", None)
    created["id"] = str(created["_id"])
    return {"id": created["id"], "name": created["name"], "email": created["email"]}


@router.post("/login")
async def login(payload: LoginRequest):
    try:
        user = db.users.find_one({"email": payload.email.lower()})
    except PyMongoError as exc:
        raise database_unavailable(exc) from exc

    if not user or not pwd_context.verify(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(str(user["_id"]))
    user_payload = {"id": str(user["_id"]), "name": user.get("name", ""), "email": user.get("email", "")}
    return {"access_token": token, "token_type": "bearer", "user": user_payload}


def create_access_token(subject: str) -> str:
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": subject, "exp": int(expire.timestamp())}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication token") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    try:
        obj_id = to_object_id(user_id)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid user token") from exc

    try:
        user = db.users.find_one({"_id": obj_id})
    except PyMongoError as exc:
        raise database_unavailable(exc) from exc
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "id": str(current_user["_id"]),
        "name": current_user.get("name", ""),
        "email": current_user.get("email", ""),
    }
