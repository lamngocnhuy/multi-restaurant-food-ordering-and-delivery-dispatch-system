from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictBool
from sqlalchemy.orm import Session

from api.auth import get_current_user
from database.connection import get_db
from models.entities import User


router = APIRouter(prefix="/api/v1/driver", tags=["Tài xế"])


class AvailabilityForm(BaseModel):
    is_online: StrictBool


def require_driver(user: User = Depends(get_current_user)) -> User:
    if user.role != "DRIVER":
        raise HTTPException(403, "Chỉ tài xế được thay đổi trạng thái nhận chuyến")
    return user


@router.get("/availability")
def get_availability(driver: User = Depends(require_driver)):
    return {"is_online": bool(driver.is_online)}


@router.put("/availability")
def update_availability(
    form: AvailabilityForm,
    db: Session = Depends(get_db),
    driver: User = Depends(require_driver),
):
    driver.is_online = form.is_online
    db.commit()
    return {"is_online": form.is_online}