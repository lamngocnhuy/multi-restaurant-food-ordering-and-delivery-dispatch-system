from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import get_current_user
from database.connection import get_db
from models.entities import User


router = APIRouter(prefix="/api/v1/admin/users", tags=["Quản lý tài khoản"])


class UserStatusForm(BaseModel):
    status: Literal["ACTIVE", "LOCKED"]


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(403, "Chỉ Admin được quản lý tài khoản")
    return user


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.full_name,
        "email": user.email,
        "role": user.role,
        "status": user.status,
    }


@router.get("")
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    users = db.query(User).order_by(User.role, User.full_name, User.id).all()
    return [serialize_user(user) for user in users]


@router.patch("/{user_id}/status")
def update_user_status(
    user_id: str,
    form: UserStatusForm,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if user is None:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    if user.role not in ("CUSTOMER", "RESTAURANT", "DRIVER"):
        raise HTTPException(403, "Không thể đổi trạng thái của tài khoản này")
    if user.status not in ("ACTIVE", "LOCKED"):
        raise HTTPException(409, "Tài khoản chưa ở trạng thái có thể khóa hoặc mở khóa")

    user.status = form.status
    result = serialize_user(user)
    db.commit()
    return result
