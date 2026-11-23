from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.auth import get_current_user
from database.connection import get_db
from models.entities import (
    DeliveryAssignment, Order, OrderReview, OrderReviewReply, Restaurant, SubOrder, User,
)


router = APIRouter(prefix="/api/v1/orders", tags=["Đánh giá"])


class ReviewForm(BaseModel):
    restaurant_stars: int = Field(ge=1, le=5)
    driver_stars: int | None = Field(default=None, ge=1, le=5)
    comment: str = Field(default="", max_length=500)


def completed_customer_order(db, user, order_id, *, lock=False):
    if user.role != "CUSTOMER":
        raise HTTPException(403, "Chỉ khách hàng được đánh giá đơn của mình")

    query = db.query(Order).filter_by(id=order_id, customer_id=user.id)
    if lock:
        query = query.with_for_update()
    order = query.one_or_none()
    if order is None:
        raise HTTPException(404, "Không tìm thấy đơn hàng")
    if order.status not in ("COMPLETED", "DELIVERED"):
        raise HTTPException(409, "Chỉ có thể đánh giá đơn đã giao")
    return order


def has_completed_delivery(db, order_id):
    return (
        db.query(DeliveryAssignment.id)
        .join(SubOrder, SubOrder.id == DeliveryAssignment.sub_order_id)
        .filter(
            SubOrder.order_id == order_id,
            DeliveryAssignment.status == "COMPLETED",
        )
        .first()
        is not None
    )


def review_data(review):
    if review is None:
        return None
    return {
        "restaurant_stars": review.restaurant_stars,
        "driver_stars": review.driver_stars,
        "comment": review.comment,
    }


@router.get("/{order_id}/review")
def get_review(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = completed_customer_order(db, user, order_id)
    return {
        "can_rate_driver": has_completed_delivery(db, order.id),
        "review": review_data(db.get(OrderReview, order.id)),
        "restaurant_replies": [
            {"restaurant_name": name, "message": message}
            for name, message in (
                db.query(Restaurant.name, OrderReviewReply.message)
                .join(Restaurant, Restaurant.id == OrderReviewReply.restaurant_id)
                .filter(OrderReviewReply.order_id == order.id)
                .order_by(Restaurant.name, Restaurant.id)
                .all()
            )
        ],
    }


@router.put("/{order_id}/review")
def save_review(
    order_id: str,
    form: ReviewForm,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = completed_customer_order(db, user, order_id, lock=True)
    can_rate_driver = has_completed_delivery(db, order.id)
    if form.driver_stars is not None and not can_rate_driver:
        raise HTTPException(422, "Đơn này chưa có chuyến giao để đánh giá")

    review = db.get(OrderReview, order.id)
    if review is None:
        review = OrderReview(order_id=order.id)
        db.add(review)

    review.restaurant_stars = form.restaurant_stars
    review.driver_stars = form.driver_stars
    review.comment = form.comment.strip()
    result = review_data(review)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Đánh giá vừa được cập nhật. Hãy mở lại form.") from None

    return {"review": result, "can_rate_driver": can_rate_driver}


class ReplyForm(BaseModel):
    message: str = Field(min_length=1, max_length=500)


def require_restaurant_owner(user: User = Depends(get_current_user)):
    if user.role != "RESTAURANT":
        raise HTTPException(403, "Chỉ chủ quán được phản hồi đánh giá")
    return user


def restaurant_rating_summary(db):
    rows = (
        db.query(
            SubOrder.restaurant_id,
            func.avg(OrderReview.restaurant_stars),
            func.count(OrderReview.order_id),
        )
        .join(OrderReview, OrderReview.order_id == SubOrder.order_id)
        .group_by(SubOrder.restaurant_id)
        .all()
    )
    return {
        restaurant_id: {"average": round(float(average), 1), "count": count}
        for restaurant_id, average, count in rows
    }


@router.get("/restaurant/reviews")
def list_restaurant_reviews(
    db: Session = Depends(get_db),
    owner: User = Depends(require_restaurant_owner),
):
    rows = (
        db.query(OrderReview, Restaurant, OrderReviewReply)
        .join(SubOrder, SubOrder.order_id == OrderReview.order_id)
        .join(Restaurant, Restaurant.id == SubOrder.restaurant_id)
        .outerjoin(
            OrderReviewReply,
            (OrderReviewReply.order_id == OrderReview.order_id)
            & (OrderReviewReply.restaurant_id == Restaurant.id),
        )
        .filter(Restaurant.owner_id == owner.id)
        .order_by(Restaurant.name, OrderReview.order_id)
        .all()
    )
    return [
        {
            "order_id": review.order_id,
            "restaurant_id": restaurant.id,
            "restaurant_name": restaurant.name,
            "stars": review.restaurant_stars,
            "comment": review.comment,
            "reply": reply.message if reply else "",
        }
        for review, restaurant, reply in rows
    ]


@router.put("/restaurant/reviews/{order_id}/{restaurant_id}/reply")
def save_restaurant_reply(
    order_id: str,
    restaurant_id: str,
    form: ReplyForm,
    db: Session = Depends(get_db),
    owner: User = Depends(require_restaurant_owner),
):
    permitted = (
        db.query(SubOrder.id)
        .join(Restaurant, Restaurant.id == SubOrder.restaurant_id)
        .filter(
            SubOrder.order_id == order_id,
            SubOrder.restaurant_id == restaurant_id,
            Restaurant.owner_id == owner.id,
        )
        .first()
    )
    if permitted is None:
        raise HTTPException(404, "Không tìm thấy đánh giá của quán")

    review = (
        db.query(OrderReview)
        .filter_by(order_id=order_id)
        .with_for_update()
        .one_or_none()
    )
    if review is None:
        raise HTTPException(404, "Đơn chưa có đánh giá")

    message = form.message.strip()
    if not message:
        raise HTTPException(422, "Vui lòng nhập phản hồi")

    reply = db.get(OrderReviewReply, (order_id, restaurant_id))
    if reply is None:
        reply = OrderReviewReply(order_id=order_id, restaurant_id=restaurant_id)
        db.add(reply)
    reply.message = message

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Phản hồi vừa thay đổi. Hãy tải lại danh sách.") from None

    return {"reply": message}
