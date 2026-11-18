import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.connection import get_db
from models.entities import User


router = APIRouter(prefix="/api/v1/auth", tags=["Tài khoản"])
bearer = HTTPBearer(auto_error=False)

PASSWORD_ITERATIONS = 600_000
TOKEN_TTL_SECONDS = 8 * 60 * 60


class RegisterForm(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)


class LoginForm(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, rounds, salt, expected = stored_hash.split("$")
        iterations = int(rounds)
        if algorithm != "pbkdf2_sha256" or not 1 <= iterations <= 1_000_000:
            return False

        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
        )
    except (AttributeError, ValueError):
        return False

    return hmac.compare_digest(digest, bytes.fromhex(expected)) if re.fullmatch(
        r"[0-9a-f]{64}", expected
    ) else False


def token_secret() -> bytes:
    secret = os.environ.get("FOOD_DISPATCH_AUTH_SECRET", "").encode("utf-8")
    if len(secret) < 32:
        raise HTTPException(503, "Máy chủ chưa cấu hình khóa đăng nhập")
    return secret


def issue_token(user_id: str) -> str:
    payload = json.dumps({
        "sub": user_id,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }).encode("utf-8")
    body = base64.urlsafe_b64encode(payload).decode("ascii")
    signature = hmac.new(
        token_secret(), body.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{body}.{signature}"


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Vui lòng đăng nhập lại",
        headers={"WWW-Authenticate": "Bearer"},
    )


def read_token(token: str) -> str:
    secret = token_secret()

    try:
        body, signature = token.split(".")
        expected = hmac.new(secret, body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise unauthorized()

        payload = json.loads(base64.urlsafe_b64decode(body))
        user_id = payload["sub"]
        expires_at = payload["exp"]
        if not isinstance(user_id, str) or not isinstance(expires_at, int):
            raise unauthorized()
        if expires_at <= int(time.time()):
            raise unauthorized()

        return user_id
    except (ValueError, TypeError, KeyError, binascii.Error):
        raise unauthorized() from None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise unauthorized()

    user = db.get(User, read_token(credentials.credentials))
    if user is None or user.status != "ACTIVE":
        raise unauthorized()
    return user


def public_user(user: User) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
    }


@router.post("/register", status_code=201)
def register(form: RegisterForm, db: Session = Depends(get_db)):
    full_name = form.full_name.strip()
    email = form.email.strip().lower()

    if not full_name:
        raise HTTPException(422, "Vui lòng nhập họ tên")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(422, "Email không hợp lệ")
    if db.query(User.id).filter(func.lower(User.email) == email).first():
        raise HTTPException(409, "Email đã được sử dụng")

    user = User(
        full_name=full_name,
        email=email,
        password_hash=hash_password(form.password),
        role="CUSTOMER",
        status="ACTIVE",
    )
    db.add(user)

    try:
        db.flush()
        result = public_user(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.query(User.id).filter(func.lower(User.email) == email).first():
            raise HTTPException(409, "Email đã được sử dụng") from None
        raise

    return result


@router.post("/login")
def login(form: LoginForm, db: Session = Depends(get_db)):
    email = form.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()

    if (
        user is None
        or user.status != "ACTIVE"
        or not verify_password(form.password, user.password_hash)
    ):
        raise HTTPException(401, "Email hoặc mật khẩu không đúng, hoặc tài khoản bị khóa")

    return {
        "access_token": issue_token(user.id),
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
        "user": public_user(user),
    }


@router.get("/me")
def get_profile(user: User = Depends(get_current_user)):
    return public_user(user)