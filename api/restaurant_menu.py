from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import get_current_user
from database.connection import get_db
from models.entities import FoodItem, Restaurant, User


router = APIRouter(prefix="/api/v1/restaurant/menu", tags=["Thực đơn nhà hàng"])


class FoodForm(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price: int = Field(ge=1, le=100_000_000)
    category: Literal["FOOD", "DRINK"]
    status: Literal["IN_STOCK", "OUT_OF_STOCK"] | None = None
    image_url: str | None = Field(default=None, max_length=1000)


def require_owner(user: User = Depends(get_current_user)) -> User:
    if user.role != "RESTAURANT":
        raise HTTPException(403, "Chỉ chủ quán được quản lý thực đơn")
    return user


def find_owned_restaurant(db, owner, restaurant_id):
    restaurant = db.query(Restaurant).filter_by(
        id=restaurant_id, owner_id=owner.id
    ).one_or_none()
    if restaurant is None:
        raise HTTPException(404, "Không tìm thấy nhà hàng của bạn")
    return restaurant


def food_data(food):
    return {
        "id": food.id,
        "restaurant_id": food.restaurant_id,
        "name": food.name,
        "price": food.price,
        "category": food.category,
        "status": food.status,
        "image_url": food.image_url,
    }


def apply_form(food, form):
    name = form.name.strip()
    if not name:
        raise HTTPException(422, "Vui lòng nhập tên món")
    if form.image_url is not None:
        image_url = form.image_url.strip()

        if image_url:
            try:
                parsed = urlsplit(image_url)
                is_local = (
                    not parsed.scheme
                    and not parsed.netloc
                    and parsed.path.startswith("/static/")
                    and not parsed.query
                    and not parsed.fragment
                )
                is_https = (
                    parsed.scheme == "https"
                    and bool(parsed.hostname)
                    and not parsed.username
                    and not parsed.password
                )
            except ValueError:
                is_local = is_https = False

            if not (is_local or is_https):
                raise HTTPException(422, "Ảnh phải dùng đường dẫn /static/ hoặc URL HTTPS")

        food.image_url = image_url or None

    food.name = name
    food.price = form.price
    food.category = form.category
    if form.status is not None:
        food.status = form.status


@router.get("")
def list_menu(
    db: Session = Depends(get_db),
    owner: User = Depends(require_owner),
):
    restaurants = (
        db.query(Restaurant)
        .filter_by(owner_id=owner.id)
        .order_by(Restaurant.name)
        .all()
    )
    foods = (
        db.query(FoodItem)
        .join(Restaurant, Restaurant.id == FoodItem.restaurant_id)
        .filter(Restaurant.owner_id == owner.id)
        .order_by(FoodItem.name)
        .all()
    )
    return {
        "restaurants": [{"id": item.id, "name": item.name} for item in restaurants],
        "foods": [food_data(food) for food in foods],
    }


@router.post("/{restaurant_id}/foods", status_code=201)
def create_food(
    restaurant_id: str,
    form: FoodForm,
    db: Session = Depends(get_db),
    owner: User = Depends(require_owner),
):
    restaurant = find_owned_restaurant(db, owner, restaurant_id)
    food = FoodItem(restaurant_id=restaurant.id, status="IN_STOCK")
    apply_form(food, form)
    db.add(food)
    db.flush()
    result = food_data(food)
    db.commit()
    return result


@router.put("/{restaurant_id}/foods/{food_id}")
def update_food(
    restaurant_id: str,
    food_id: str,
    form: FoodForm,
    db: Session = Depends(get_db),
    owner: User = Depends(require_owner),
):
    restaurant = find_owned_restaurant(db, owner, restaurant_id)
    food = db.query(FoodItem).filter_by(
        id=food_id, restaurant_id=restaurant.id
    ).one_or_none()
    if food is None:
        raise HTTPException(404, "Không tìm thấy món trong thực đơn của quán")

    apply_form(food, form)
    result = food_data(food)
    db.commit()
    return result