import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.admin_users import require_admin
from api.auth import hash_password
from database.connection import get_db
from models.entities import Restaurant, RestaurantApplication, User


router = APIRouter(prefix="/api/v1/partners", tags=["Nhà hàng đối tác"])


class PartnerForm(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)
    restaurant_name: str = Field(min_length=1, max_length=150)
    address: str = Field(min_length=5, max_length=500)


class DecisionForm(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]


@router.post("/applications", status_code=201)
def submit_application(form: PartnerForm, db: Session = Depends(get_db)):
    email = form.email.strip().lower()
    full_name = form.full_name.strip()
    restaurant_name = form.restaurant_name.strip()
    address = form.address.strip()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(422, "Email không hợp lệ")
    if not full_name or not restaurant_name or len(address) < 5:
        raise HTTPException(422, "Vui lòng nhập tên người liên hệ, tên quán và địa chỉ")
    if db.query(User.id).filter(func.lower(User.email) == email).first():
        raise HTTPException(409, "Email đã được sử dụng")

    owner = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password(form.password),
        role="RESTAURANT",
        status="PENDING",
        is_online=False,
    )
    db.add(owner)

    try:
        db.flush()
        db.add(RestaurantApplication(
            owner_id=owner.id,
            restaurant_name=restaurant_name,
            address=address,
            status="PENDING",
        ))
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.query(User.id).filter(func.lower(User.email) == email).first():
            raise HTTPException(409, "Email đã được sử dụng") from None
        raise

    return {"status": "PENDING", "message": "Đã gửi hồ sơ. Vui lòng chờ Admin duyệt."}


@router.get("/applications")
def list_applications(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    rows = (
        db.query(RestaurantApplication, User)
        .join(User, User.id == RestaurantApplication.owner_id)
        .order_by(RestaurantApplication.created_at.desc())
        .all()
    )

    return [
        {
            "owner_id": owner.id,
            "full_name": owner.full_name,
            "email": owner.email,
            "restaurant_name": application.restaurant_name,
            "address": application.address,
            "status": application.status,
        }
        for application, owner in rows
    ]


@router.patch("/applications/{owner_id}")
def decide_application(
    owner_id: str,
    form: DecisionForm,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    application = db.get(RestaurantApplication, owner_id)
    if application is None:
        raise HTTPException(404, "Không tìm thấy hồ sơ")
    if application.status == form.decision:
        return {"status": application.status}

    # Chỉ một yêu cầu có thể chuyển hồ sơ khỏi trạng thái PENDING.
    changed = (
        db.query(RestaurantApplication)
        .filter_by(owner_id=owner_id, status="PENDING")
        .update({"status": form.decision}, synchronize_session=False)
    )
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "Hồ sơ đã được xử lý. Vui lòng tải lại.")

    owner = db.get(User, owner_id)
    if owner is None or owner.role != "RESTAURANT" or owner.status != "PENDING":
        db.rollback()
        raise HTTPException(409, "Tài khoản chủ quán không còn ở trạng thái chờ duyệt")

    if form.decision == "APPROVED":
        owner.status = "ACTIVE"
        db.add(Restaurant(
            owner_id=owner.id,
            name=application.restaurant_name,
            address=application.address,
            status="OPEN",
        ))
    else:
        owner.status = "REJECTED"

    db.commit()
    return {"status": form.decision}
