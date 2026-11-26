from typing import Literal

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
    }


def apply_form(food, form):
    name = form.name.strip()
    if not name:
        raise HTTPException(422, "Vui lòng nhập tên món")

    food.name = name
    food.price = form.price
    food.category = form.category


@router.get("")
def list_menu(
    db: Session = Depends(get_db),
    owner: User = Depends(require_owner),
):
    restaurants = db.query(Restaurant).filter_by(
        owner_id=owner.id
    ).order_by(Restaurant.name).all()

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