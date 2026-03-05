"""
routers/auth.py – JWT authentication (register, login, me).
"""

import os
import hashlib
import hmac
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from jose import jwt, JWTError
from dotenv import load_dotenv

from database import users_collection
from schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse

load_dotenv()

router = APIRouter(prefix="/api/auth", tags=["auth"])

JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_in_production_min32chars!!")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24


def _hash_password(password: str) -> str:
    """Simple SHA-256 hash (use bcrypt in production)."""
    return hashlib.sha256(password.encode()).hexdigest()


def _verify_password(password: str, hashed: str) -> bool:
    return hmac.compare_digest(_hash_password(password), hashed)


def _create_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    """Dependency: extract and verify JWT from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await users_collection.find_one({"email": payload["email"]})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/register")
async def register(req: RegisterRequest):
    """Create a new user account."""
    existing = await users_collection.find_one({"email": req.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_doc = {
        "email": req.email,
        "password_hash": _hash_password(req.password),
        "name": req.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await users_collection.insert_one(user_doc)

    user_id = str(result.inserted_id)
    token = _create_token(user_id, req.email)

    return {
        "access_token": token,
        "user": {"id": user_id, "email": req.email, "name": req.name}
    }


@router.post("/login")
async def login(req: LoginRequest):
    """Authenticate and return JWT."""
    user = await users_collection.find_one({"email": req.email})
    if not user or not _verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_id = str(user["_id"])
    token = _create_token(user_id, req.email)

    return {
        "access_token": token,
        "user": {"id": user_id, "email": user["email"], "name": user["name"]}
    }


@router.get("/me")
async def me(user=Depends(get_current_user)):
    """Return current user profile."""
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": user["name"],
    }
