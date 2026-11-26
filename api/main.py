from api.auth import get_current_user, router as auth_router
from api.partner_applications import router as partner_applications_router
from api.order_reviews import (
    restaurant_rating_summary,
    router as order_reviews_router,
)
from api.admin_users import router as admin_users_router
from api.driver_availability import router as driver_availability_router
from datetime import timedelta
from pathlib import Path
from threading import Lock
from api.restaurant_menu import router as restaurant_menu_router
from fastapi import BackgroundTasks, Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from database.connection import Base, SessionLocal, engine, get_db
from forms.schemas import AddToCartForm, CheckoutForm
from models.entities import (
    Cart,
    CartItem,
    CheckoutGroupOrder,
    DeliveryAssignment,
    DeliverySimulation,
    DeliveryFailure,
    FoodItem,
    Order,
    OrderItem,
    Payment,
    Restaurant,
    SubOrder,
    User,
)
from services.dispatch_service import (
    DISPATCH_TIMEOUT_SECONDS,
    run_auto_dispatch_loop,
    trigger_refund_if_paid_online,
    utc_now,
)


ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "asset"
INCLUDES_DIR = ROOT / "includes"
INDEX_FILE = ROOT / "controls" / "index.html"
DELIVERY_FEE = 15_000

REGULAR_SIZE = {"id": "REGULAR", "label": "Size thường", "extra": 0}
LARGE_SIZE = {"id": "LARGE", "label": "Size lớn", "extra": 10000}
NO_TOPPING = {"id": "NONE", "label": "Không thêm topping", "extra": 0}
PEARLS = {"id": "PEARLS", "label": "Trân châu", "extra": 5000}


def food_options(category):
    if category == "DRINK":
        return {"sizes": [REGULAR_SIZE, LARGE_SIZE], "toppings": [NO_TOPPING, PEARLS]}
    return {"sizes": [REGULAR_SIZE], "toppings": [NO_TOPPING]}


def price_food_options(food, form):
    choices = food_options(food.category)
    size = next((item for item in choices["sizes"] if item["id"] == form.size), None)
    topping = next((item for item in choices["toppings"] if item["id"] == form.topping), None)
    if size is None or topping is None:
        raise HTTPException(400, "Tùy chọn không áp dụng cho món này")

    note = (form.options_note or "").strip()
    if len(note) > 200:
        raise HTTPException(400, "Ghi chú tối đa 200 ký tự")

    details = []
    if size["extra"]:
        details.append(size["label"])
    if topping["extra"]:
        details.append(topping["label"])
    if note:
        details.append(f"Ghi chú: {note}")

    return food.price + size["extra"] + topping["extra"], " · ".join(details)
SEED_LOCK = Lock()

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Multi-Restaurant Food Ordering & Delivery Dispatch System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if ASSET_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=ASSET_DIR), name="static")

app.mount("/includes", StaticFiles(directory=INCLUDES_DIR), name="includes")


app.include_router(auth_router)
app.include_router(partner_applications_router)
app.include_router(order_reviews_router)
app.include_router(admin_users_router)
app.include_router(driver_availability_router)
app.include_router(restaurant_menu_router)


@app.get("/")
def serve_web_app():
    if INDEX_FILE.is_file():
        return FileResponse(INDEX_FILE)
    return {"message": "Backend API đang hoạt động. Truy cập /docs để xem tài liệu API."}


def require_role(user, *roles):
    if user.role not in roles:
        raise HTTPException(403, "Tài khoản không có quyền thực hiện thao tác này")


def require_customer(user, customer_id):
    require_role(user, "CUSTOMER")
    if user.id != customer_id:
        raise HTTPException(403, "Bạn chỉ được truy cập dữ liệu của mình")


def require_restaurant(db, user, sub):
    require_role(user, "RESTAURANT")
    restaurant = db.get(Restaurant, sub.restaurant_id) if sub else None
    if restaurant is None or restaurant.owner_id != user.id:
        raise HTTPException(404, "Không tìm thấy đơn của nhà hàng")


@app.post("/api/v1/seed")
def seed_sample_data(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_role(user, "ADMIN")

    def ensure_user(email, role, full_name, **extra):
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                email=email,
                role=role,
                full_name=full_name,
                password_hash="hashed_pass",
                **extra,
            )
            db.add(user)
            db.flush()
        return user

    def ensure_restaurant(owner, name, address, menu):
        restaurant = db.query(Restaurant).filter(
            Restaurant.owner_id == owner.id,
            Restaurant.name == name,
        ).first()

        if restaurant is None:
            restaurant = Restaurant(owner_id=owner.id, name=name, address=address)
            db.add(restaurant)
            db.flush()

        existing_names = {
            name for (name,) in db.query(FoodItem.name).filter(
                FoodItem.restaurant_id == restaurant.id
            )
        }
        for food_name, price in menu:
            if food_name not in existing_names:
                db.add(FoodItem(
                    restaurant_id=restaurant.id,
                    name=food_name,
                    price=price,
                ))

    with SEED_LOCK:
        try:
            customer = ensure_user("khach1@gmail.com", "CUSTOMER", "Nguyễn Văn A")
            pho_owner = ensure_user("pho@gmail.com", "RESTAURANT", "Chủ Quán Phở Hà Nội")
            rice_owner = ensure_user(
                "comtam@gmail.com", "RESTAURANT", "Chủ Quán Cơm Tấm Sài Gòn"
            )
            driver = ensure_user(
                "driver1@gmail.com", "DRIVER", "Tài xế Trần Văn B", is_online=True
            )
            ensure_user(
                "driver2@gmail.com", "DRIVER", "Tài xế Lê Văn C", is_online=True
            )

            ensure_restaurant(
                pho_owner,
                "Phở Bò Gia Truyền Hà Nội",
                "19 Nguyễn Hữu Thọ, Q.7",
                [("Phở Bò Tái Nạm", 45000), ("Phở Đặc Biệt Bát Đá", 65000)],
            )
            ensure_restaurant(
                rice_owner,
                "Cơm Tấm Sườn Bì Chả",
                "45 Lê Văn Lương, Q.7",
                [("Cơm Tấm Sườn Cốt Lết", 40000), ("Cơm Tấm Sườn Bì Chả Trứng", 55000)],
            )

            customer_id, driver_id = customer.id, driver.id
            db.commit()
        except Exception:
            db.rollback()
            raise

    return {
        "message": "Dữ liệu mẫu đã sẵn sàng",
        "customer_id": customer_id,
        "driver_id": driver_id,
    }


@app.get("/api/v1/restaurants")
def list_menu_restaurants(db: Session = Depends(get_db)):
    restaurants = (
        db.query(Restaurant.id, Restaurant.name)
        .join(FoodItem, FoodItem.restaurant_id == Restaurant.id)
        .distinct()
        .order_by(Restaurant.name, Restaurant.id)
        .all()
    )
    return [{"id": item.id, "name": item.name} for item in restaurants]


@app.get("/api/v1/menu")
def get_menu(
    keyword: str = "",
    category: str = "",
    restaurant_id: str = "",
    db: Session = Depends(get_db),
):
    if category not in ("", "FOOD", "DRINK"):
        raise HTTPException(422, "Phân loại thực đơn không hợp lệ")

    query = db.query(FoodItem, Restaurant).join(
        Restaurant, FoodItem.restaurant_id == Restaurant.id
    )
    keyword = keyword.strip()
    if keyword:
        query = query.filter(
            FoodItem.name.icontains(keyword, autoescape=True)
            | Restaurant.name.icontains(keyword, autoescape=True)
        )
    if category:
        query = query.filter(FoodItem.category == category)
    if restaurant_id:
        query = query.filter(Restaurant.id == restaurant_id)

    ratings = restaurant_rating_summary(db)
    return [
        {
            "id": food.id,
            "name": food.name,
            "price": food.price,
            "category": food.category,
            "options": food_options(food.category),
            "status": food.status,
            "image_url": food.image_url,
            "restaurant_id": restaurant.id,
            "restaurant_name": restaurant.name,
            "restaurant_status": restaurant.status,
            "restaurant_rating": ratings.get(restaurant.id),
        }
        for food, restaurant in query.order_by(Restaurant.name, FoodItem.name).all()
    ]


def lock_customer(db: Session, customer_id: str):
    customer = db.query(User).filter(
        User.id == customer_id,
        User.role == "CUSTOMER",
    ).with_for_update().first()
    if customer is None:
        raise HTTPException(404, "Không tìm thấy khách hàng")
    return customer


@app.post("/api/v1/cart/items")
def add_to_cart(form: AddToCartForm, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_customer(user, form.customer_id)
    if not 1 <= form.quantity <= 99:
        raise HTTPException(400, "Số lượng phải từ 1 đến 99")
    if form.size_extra != 0 or form.topping_extra != 0:
        raise HTTPException(400, "Vui lòng gửi mã tùy chọn để hệ thống tính phụ phí")

    lock_customer(db, form.customer_id)

    food = db.query(FoodItem).filter(FoodItem.id == form.food_id).first()
    if food is None:
        raise HTTPException(404, "Món ăn không tồn tại")
    restaurant = db.get(Restaurant, food.restaurant_id)
    if restaurant is None or restaurant.status == "CLOSED":
        raise HTTPException(400, "Quán đang tạm ngừng nhận đơn")
    if food.status == "OUT_OF_STOCK":
        raise HTTPException(400, f"Món {food.name} đã hết")

    cart = db.query(Cart).filter(Cart.customer_id == form.customer_id).first()
    if cart is None:
        cart = Cart(
            customer_id=form.customer_id,
            total_amount=0,
        )
        db.add(cart)
        db.flush()

    item_query = db.query(CartItem).filter(CartItem.cart_id == cart.id)

    unit_price, options_note = price_food_options(food, form)
    item = item_query.filter(CartItem.food_id == food.id).first()

    if item is None:
        db.add(CartItem(
            cart_id=cart.id,
            food_id=food.id,
            quantity=form.quantity,
            unit_price=unit_price,
            options_note=options_note,
        ))
    else:
        if item.quantity + form.quantity > 99:
            raise HTTPException(400, "Mỗi món chỉ được có tối đa 99 phần trong giỏ")

        if (item.options_note or "") != options_note:
            raise HTTPException(
                400, "Món đã có tùy chọn khác trong giỏ. Hãy xóa dòng cũ rồi thêm lại."
            )
        item.quantity += form.quantity
        item.unit_price = unit_price

    db.flush()
    total = sum(row.quantity * row.unit_price for row in item_query.all())
    cart.total_amount = total
    db.commit()
    return {"message": "Đã thêm vào giỏ hàng", "total_amount": total}


@app.put("/api/v1/cart/items/{item_id}")
def update_cart_item(
    item_id: str,
    quantity: int = Body(..., embed=True, ge=0, le=99),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_role(user, "CUSTOMER")
    lock_customer(db, user.id)

    cart = db.query(Cart).filter(Cart.customer_id == user.id).first()
    if cart is None:
        raise HTTPException(404, "Không tìm thấy món trong giỏ của bạn")

    items = db.query(CartItem).filter(CartItem.cart_id == cart.id)
    item = items.filter(CartItem.id == item_id).first()
    if item is None:
        raise HTTPException(404, "Không tìm thấy món trong giỏ của bạn")

    if quantity == 0:
        db.delete(item)
    else:
        if quantity > item.quantity:
            food = db.get(FoodItem, item.food_id)
            if food is None or food.status == "OUT_OF_STOCK":
                raise HTTPException(409, "Món đã hết. Bạn có thể giảm số lượng hoặc xóa món.")
            restaurant = db.get(Restaurant, food.restaurant_id)
            if restaurant is None or restaurant.status == "CLOSED":
                raise HTTPException(409, "Quán đang tạm đóng. Bạn có thể giảm số lượng hoặc xóa món.")
        item.quantity = quantity

    db.flush()
    remaining = items.all()
    total = sum(row.quantity * row.unit_price for row in remaining)
    cart.total_amount = total
    if not remaining:
        cart.restaurant_id = None

    db.commit()
    return {"quantity": quantity, "total_amount": total}


def grouped_cart_rows(db, cart_id):
    rows = (
        db.query(CartItem, FoodItem, Restaurant)
        .join(FoodItem, CartItem.food_id == FoodItem.id)
        .join(Restaurant, FoodItem.restaurant_id == Restaurant.id)
        .filter(CartItem.cart_id == cart_id)
        .order_by(Restaurant.name, Restaurant.id, FoodItem.name, CartItem.id)
        .all()
    )
    groups = {}
    for item, food, restaurant in rows:
        groups.setdefault(restaurant.id, []).append((item, food, restaurant))
    return groups


@app.get("/api/v1/cart/{customer_id}")
def get_cart(
    customer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_customer(user, customer_id)
    cart = db.query(Cart).filter_by(customer_id=customer_id).first()
    if cart is None:
        return {"items": [], "groups": [], "total_amount": 0}

    groups = []
    for restaurant_id, rows in grouped_cart_rows(db, cart.id).items():
        items = []
        for item, food, restaurant in rows:
            items.append({
                "id": item.id,
                "food_id": food.id,
                "food_name": food.name,
                "image_url": food.image_url,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "options_note": item.options_note,
                "available": food.status != "OUT_OF_STOCK" and restaurant.status != "CLOSED",
            })
        groups.append({
            "restaurant_id": restaurant_id,
            "restaurant_name": rows[0][2].name,
            "subtotal": sum(item.quantity * item.unit_price for item, _, _ in rows),
            "delivery_fee": DELIVERY_FEE,
            "items": items,
        })

    return {
        "cart_id": cart.id,
        "restaurant_id": groups[0]["restaurant_id"] if len(groups) == 1 else None,
        "total_amount": sum(group["subtotal"] for group in groups),
        "items": [item for group in groups for item in group["items"]],
        "groups": groups,
    }


class GroupCheckoutForm(CheckoutForm):
    restaurant_ids: list[str] | None = None


@app.post("/api/v1/orders/checkout")
def checkout(
    form: GroupCheckoutForm,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_customer(user, form.customer_id)
    address = (form.delivery_address or "").strip()
    if len(address) < 5:
        raise HTTPException(400, "Vui lòng nhập đầy đủ địa chỉ giao hàng")
    if form.payment_method not in ("COD", "ONLINE"):
        raise HTTPException(400, "Phương thức thanh toán không hợp lệ")

    lock_customer(db, user.id)
    cart = db.query(Cart).filter_by(customer_id=user.id).first()
    groups = grouped_cart_rows(db, cart.id) if cart else {}
    if not groups:
        raise HTTPException(400, "Giỏ hàng trống")

    if form.restaurant_ids is None:
        if len(groups) != 1:
            raise HTTPException(400, "Vui lòng chọn giỏ muốn đặt")
        selected = list(groups)
    else:
        selected = list(dict.fromkeys(form.restaurant_ids))

    if not selected:
        raise HTTPException(400, "Vui lòng chọn ít nhất một giỏ")
    if any(restaurant_id not in groups for restaurant_id in selected):
        raise HTTPException(409, "Giỏ hàng đã thay đổi. Vui lòng chọn lại.")

    for restaurant_id in selected:
        rows = groups[restaurant_id]
        restaurant = rows[0][2]
        if restaurant.status == "CLOSED":
            raise HTTPException(
                409, f"Quán {restaurant.name} đang tạm đóng. Hãy bỏ chọn giỏ của quán."
            )
        for _, food, _ in rows:
            if food.status == "OUT_OF_STOCK":
                raise HTTPException(409, f"Món {food.name} đã hết. Vui lòng xóa món khỏi giỏ.")

    placed = []
    for restaurant_id in selected:
        rows = groups[restaurant_id]
        subtotal = sum(item.quantity * item.unit_price for item, _, _ in rows)

        order = Order(
            customer_id=user.id,
            delivery_address=address,
            grand_total=subtotal + DELIVERY_FEE,
            status="PENDING",
        )
        db.add(order)
        db.flush()

        sub = SubOrder(
            order_id=order.id,
            restaurant_id=restaurant_id,
            subtotal=subtotal,
            status="PENDING",
        )
        db.add(sub)
        db.flush()

        for item, _, _ in rows:
            db.add(OrderItem(
                sub_order_id=sub.id,
                food_id=item.food_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.quantity * item.unit_price,
                options_note=item.options_note,
            ))
            db.delete(item)

        db.add(Payment(
            order_id=order.id,
            method=form.payment_method,
            amount=order.grand_total,
            status="PENDING",
        ))
        placed.append({
            "order_id": order.id,
            "sub_order_id": sub.id,
            "restaurant_id": restaurant_id,
            "grand_total": order.grand_total,
        })

    group_id = placed[0]["order_id"] if len(placed) > 1 else None
    if group_id:
        for entry in placed:
            db.add(CheckoutGroupOrder(order_id=entry["order_id"], group_id=group_id))

    selected_set = set(selected)
    remaining = {
        restaurant_id: rows for restaurant_id, rows in groups.items()
        if restaurant_id not in selected_set
    }
    cart.total_amount = sum(
        item.quantity * item.unit_price
        for rows in remaining.values() for item, _, _ in rows
    )
    cart.restaurant_id = next(iter(remaining)) if len(remaining) == 1 else None
    db.commit()

    return {
        "message": "Đặt hàng thành công",
        "group_id": group_id,
        "orders": placed,
        "order_id": placed[0]["order_id"],
        "sub_order_id": placed[0]["sub_order_id"],
    }


def simulated_driver_location(db, order, user):
    if user.role != "CUSTOMER" or order.status != "DELIVERING":
        return None

    simulation = db.get(DeliverySimulation, order.id)
    if simulation is None:
        return None

    elapsed = (utc_now() - simulation.started_at).total_seconds()
    fraction = min(1.0, max(0.0, elapsed / 180))
    latitude = min(90.0, simulation.start_latitude + 0.006 * fraction)
    longitude = min(180.0, simulation.start_longitude + 0.008 * fraction)

    return {
        "latitude": round(latitude, 5),
        "longitude": round(longitude, 5),
        "simulated": True,
        "demo_route_finished": fraction == 1.0,
    }


@app.get("/api/v1/orders")
def list_all_orders(customer_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Order).order_by(Order.created_at.desc())
    require_role(user, "CUSTOMER", "RESTAURANT", "DRIVER", "ADMIN")
    if user.role == "CUSTOMER":
        query = query.filter(Order.customer_id == user.id)
    elif user.role == "RESTAURANT":
        owned = db.query(SubOrder.order_id).join(
            Restaurant, Restaurant.id == SubOrder.restaurant_id
        ).filter(Restaurant.owner_id == user.id)
        query = query.filter(Order.id.in_(owned))
    elif user.role == "DRIVER":
        assigned = db.query(SubOrder.order_id).join(
            DeliveryAssignment, DeliveryAssignment.sub_order_id == SubOrder.id
        ).filter(
            DeliveryAssignment.driver_id == user.id,
            DeliveryAssignment.status.in_(("OFFERED", "ACCEPTED", "COMPLETED", "FAILED")),
        )
        query = query.filter(Order.id.in_(assigned))
    elif customer_id:
        query = query.filter(Order.customer_id == customer_id)

    orders = query.all()
    items_by_sub_order = {}

    if orders:
        rows = (
            db.query(OrderItem, FoodItem.name)
            .join(SubOrder, SubOrder.id == OrderItem.sub_order_id)
            .outerjoin(FoodItem, FoodItem.id == OrderItem.food_id)
            .filter(SubOrder.order_id.in_([order.id for order in orders]))
            .order_by(OrderItem.id)
            .all()
        )

        for item, food_name in rows:
            items_by_sub_order.setdefault(item.sub_order_id, []).append({
                "name": food_name or "Món đã lưu trong đơn",
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "line_total": item.total_price,
                "options_note": item.options_note,
            })

    failures = {}
    if orders:
        failures = dict(
            db.query(DeliveryFailure.order_id, DeliveryFailure.reason)
            .filter(DeliveryFailure.order_id.in_([order.id for order in orders]))
            .all()
        )

    output = []
    for order in orders:
        sub = db.query(SubOrder).filter(SubOrder.order_id == order.id).first()
        payment = db.query(Payment).filter(Payment.order_id == order.id).first()
        assignment = None

        if sub is not None:
            assignment = db.query(DeliveryAssignment).filter(
                DeliveryAssignment.sub_order_id == sub.id,
                DeliveryAssignment.status.in_(["OFFERED", "ACCEPTED", "COMPLETED", "FAILED"]),
            )
            if user.role == "DRIVER":
                assignment = assignment.filter(DeliveryAssignment.driver_id == user.id)
            assignment = assignment.order_by(DeliveryAssignment.assigned_at.desc()).first()

        group = db.get(CheckoutGroupOrder, order.id) if user.role == "CUSTOMER" else None
        output.append({
            "order_id": order.id,
            "checkout_group_id": group.group_id if group else None,
            "restaurant_name": (
                db.query(Restaurant.name).filter_by(id=sub.restaurant_id).scalar()
                if sub and user.role == "CUSTOMER"
                else None
            ),
            "sub_order_id": sub.id if sub else None,
            "items": items_by_sub_order.get(sub.id, []) if sub else [],
            "delivery_address": order.delivery_address,
            "driver_location": simulated_driver_location(db, order, user),
            "grand_total": order.grand_total,
            "status": order.status,
            "delivery_failure_reason": failures.get(order.id),
            "dispatch_status": sub.dispatch_status if sub else None,
            "payment_method": payment.method if payment else "COD",
            "payment_status": payment.status if payment else "PENDING",
            "assignment_id": assignment.id if assignment else None,
            "assignment_status": assignment.status if assignment else "NONE",
            "assignment_expires_at": (
                (assignment.assigned_at + timedelta(
                    seconds=DISPATCH_TIMEOUT_SECONDS
                )).isoformat(timespec="milliseconds") + "Z"
                if assignment
                and assignment.status == "OFFERED"
                and assignment.assigned_at is not None
                else None
            ),
        })

    return output


def lock_order(db: Session, order_id: str):
    order = db.query(Order).filter(
        Order.id == order_id
    ).with_for_update().first()
    if order is None:
        raise HTTPException(404, "Không tìm thấy đơn hàng")
    return order


def find_sub_order(db: Session, order_id: str):
    return db.query(SubOrder).filter(SubOrder.order_id == order_id).first()


@app.post("/api/v1/orders/{order_id}/restaurant-accept")
def restaurant_accept_order(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_role(user, "RESTAURANT")
    order = lock_order(db, order_id)
    sub = find_sub_order(db, order.id)
    require_restaurant(db, user, sub)

    if order.status != "PENDING":
        raise HTTPException(409, "Đơn hàng không ở trạng thái chờ xác nhận")

    payment = db.query(Payment).filter(Payment.order_id == order.id).first()
    if payment and payment.method == "ONLINE" and payment.status != "SUCCESS":
        raise HTTPException(409, "Đơn đang chờ khách thanh toán")

    order.status = "PREPARING"
    sub.status = "PREPARING"
    db.commit()
    return {"message": "Nhà hàng đã nhận đơn và bắt đầu chế biến."}


@app.post("/api/v1/orders/{order_id}/restaurant-ready")
def restaurant_mark_ready(
    order_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_role(user, "RESTAURANT")
    order = lock_order(db, order_id)
    sub = find_sub_order(db, order.id)
    require_restaurant(db, user, sub)

    if order.status != "PREPARING" or sub.status != "PREPARING":
        raise HTTPException(409, "Chỉ có thể báo sẵn sàng khi đơn đang chế biến")

    already_dispatching = sub.dispatch_status == "SEARCHING"
    order.status = "READY"
    sub.status = "READY"
    sub.dispatch_status = "SEARCHING"
    sub_id = sub.id
    db.commit()

    if not already_dispatching:
        background_tasks.add_task(run_auto_dispatch_loop, sub_id, SessionLocal)

    return {"message": "Món đã sẵn sàng. Hệ thống đang tìm tài xế."}


@app.post("/api/v1/orders/{order_id}/cancel")
def cancel_order(order_id: str, role: str = "CUSTOMER", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_role(user, "CUSTOMER", "RESTAURANT")
    if role != user.role:
        raise HTTPException(403, "Vai trò không khớp với tài khoản")

    order = lock_order(db, order_id)
    sub = find_sub_order(db, order.id)
    if user.role == "CUSTOMER":
        require_customer(user, order.customer_id)
    else:
        require_restaurant(db, user, sub)
    if order.status != "PENDING":
        raise HTTPException(400, "Chỉ có thể hủy hoặc từ chối đơn đang chờ xác nhận")

    order.status = "CANCELLED"

    if sub:
        sub.status = "CANCELLED"
        db.query(DeliveryAssignment).filter(
            DeliveryAssignment.sub_order_id == sub.id,
            DeliveryAssignment.status == "OFFERED",
        ).update({"status": "CANCELLED"}, synchronize_session=False)

    refunded = trigger_refund_if_paid_online(db, order.id)
    if not refunded:
        payment = db.query(Payment).filter(
            Payment.order_id == order.id,
            Payment.method == "ONLINE",
            Payment.status == "PENDING",
        ).first()
        if payment:
            payment.status = "CANCELLED"
    db.commit()

    return {
        "message": (
            "Đã hủy đơn hàng và kích hoạt quy trình hoàn tiền ST-09."
            if refunded else "Đã hủy đơn hàng."
        ),
        "refund_triggered": refunded,
    }


@app.post("/api/v1/dispatch/{assignment_id}/accept")
def driver_accept_trip(assignment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_role(user, "DRIVER")
    assignment_order = db.query(SubOrder.order_id).join(
        DeliveryAssignment, DeliveryAssignment.sub_order_id == SubOrder.id
    ).filter(
        DeliveryAssignment.id == assignment_id,
        DeliveryAssignment.driver_id == user.id,
    ).first()

    if assignment_order is None:
        raise HTTPException(400, "Đề nghị giao hàng không tồn tại")

    order = lock_order(db, assignment_order[0])
    assignment = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.id == assignment_id,
        DeliveryAssignment.driver_id == user.id,
    ).with_for_update().first()

    if assignment is None or assignment.status != "OFFERED":
        raise HTTPException(400, "Đề nghị giao hàng đã hết hạn hoặc đã được xử lý")

    sub = db.query(SubOrder).filter(SubOrder.id == assignment.sub_order_id).first()
    if (
        sub is None
        or sub.status not in ("PREPARING", "READY")
        or order.status not in ("PREPARING", "READY")
    ):
        raise HTTPException(400, "Đơn hàng không còn ở trạng thái có thể nhận giao")

    if (
        assignment.assigned_at is None
        or utc_now() >= assignment.assigned_at + timedelta(seconds=DISPATCH_TIMEOUT_SECONDS)
    ):
        raise HTTPException(409, "Đề nghị giao hàng đã hết hạn")

    existing = db.query(DeliveryAssignment.id).filter(
        DeliveryAssignment.sub_order_id == sub.id,
        DeliveryAssignment.status == "ACCEPTED",
    ).first()
    if existing is not None:
        raise HTTPException(409, "Đơn đã có tài xế nhận chuyến")

    assignment.status = "ACCEPTED"
    sub.dispatch_status = "ASSIGNED"
    sub.status = "READY"
    order.status = "READY"
    db.commit()
    return {"message": "Đã nhận chuyến. Hãy xác nhận sau khi lấy hàng."}


@app.post("/api/v1/dispatch/{assignment_id}/reject")
def driver_reject_trip(assignment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_role(user, "DRIVER")
    assignment = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.id == assignment_id,
        DeliveryAssignment.driver_id == user.id,
    ).with_for_update().first()

    if assignment is None or assignment.status != "OFFERED":
        raise HTTPException(400, "Đề nghị giao hàng đã hết hạn hoặc đã được xử lý")

    assignment.status = "REJECTED"
    db.commit()
    return {"message": "Tài xế đã từ chối chuyến. Hệ thống sẽ tìm tài xế khác."}


@app.post("/api/v1/orders/{order_id}/retry-dispatch")
def retry_dispatch(
    order_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    order = lock_order(db, order_id)
    require_customer(user, order.customer_id)
    sub = find_sub_order(db, order.id)
    if sub is None:
        raise HTTPException(404, "Không tìm thấy đơn của nhà hàng")
    if (
        order.status not in ("PREPARING", "READY")
        or sub.status not in ("PREPARING", "READY")
        or sub.dispatch_status != "FAILED"
    ):
        raise HTTPException(400, "Đơn hàng không ở trạng thái thiếu tài xế")

    sub.dispatch_status = "SEARCHING"
    sub_id = sub.id
    db.commit()

    background_tasks.add_task(run_auto_dispatch_loop, sub_id, SessionLocal)
    return {"message": "Hệ thống đang tìm lại tài xế!"}


@app.post("/api/v1/orders/{order_id}/pickup")
def confirm_pickup(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_role(user, "DRIVER")
    order = lock_order(db, order_id)
    sub = find_sub_order(db, order.id)

    assignment = db.query(DeliveryAssignment.id).filter(
        DeliveryAssignment.sub_order_id == (sub.id if sub else None),
        DeliveryAssignment.driver_id == user.id,
        DeliveryAssignment.status == "ACCEPTED",
    ).first()
    if assignment is None:
        raise HTTPException(404, "Không tìm thấy chuyến giao của bạn")

    if order.status == "DELIVERING" and sub.status == "DELIVERING":
        return {"message": "Chuyến đã được xác nhận lấy hàng"}
    if order.status != "READY" or sub.status != "READY":
        raise HTTPException(409, "Đơn chưa ở trạng thái có thể lấy hàng")

    sub.status = "DELIVERING"
    order.status = "DELIVERING"

    restaurant = db.get(Restaurant, sub.restaurant_id)
    if (
        restaurant is not None
        and restaurant.latitude is not None
        and restaurant.longitude is not None
        and -90 <= restaurant.latitude <= 90
        and -180 <= restaurant.longitude <= 180
        and db.get(DeliverySimulation, order.id) is None
    ):
        db.add(DeliverySimulation(
            order_id=order.id,
            started_at=utc_now(),
            start_latitude=restaurant.latitude,
            start_longitude=restaurant.longitude,
        ))

    db.commit()
    return {"message": "Đã lấy hàng. Đơn đang được giao."}


@app.post("/api/v1/orders/{order_id}/complete")
def complete_delivery(order_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_role(user, "DRIVER")
    order = lock_order(db, order_id)
    if order.status != "DELIVERING":
        raise HTTPException(400, "Chỉ hoàn tất được đơn đang giao")

    sub = find_sub_order(db, order.id)
    assignment = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.sub_order_id == (sub.id if sub else None),
        DeliveryAssignment.driver_id == user.id,
        DeliveryAssignment.status == "ACCEPTED",
    ).first()
    if assignment is None:
        raise HTTPException(404, "Không tìm thấy chuyến giao của bạn")

    payment = db.query(Payment).filter(Payment.order_id == order.id).first()

    order.status = "COMPLETED"
    if sub:
        sub.status = "COMPLETED"
        db.query(DeliveryAssignment).filter(
            DeliveryAssignment.sub_order_id == sub.id,
            DeliveryAssignment.status == "ACCEPTED",
        ).update({"status": "COMPLETED"}, synchronize_session=False)

    if payment and payment.method == "COD":
        payment.status = "SUCCESS"

    db.commit()
    return {"message": "Giao hàng hoàn tất"}


@app.post("/api/v1/orders/{order_id}/mock-payment/{action}")
def update_mock_payment(
    order_id: str,
    action: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if action == "confirm":
        require_role(user, "CUSTOMER")
        order_status, before, after = "PENDING", "PENDING", "SUCCESS"
    elif action == "refund":
        require_role(user, "ADMIN")
        order_status, before, after = "CANCELLED", "REFUND_PROCESSING", "REFUNDED"
    else:
        raise HTTPException(404, "Không tìm thấy thao tác thanh toán")

    order = lock_order(db, order_id)
    if action == "confirm":
        require_customer(user, order.customer_id)

    payment = db.query(Payment).filter(
        Payment.order_id == order.id,
        Payment.method == "ONLINE",
    ).first()

    if payment is None:
        raise HTTPException(404, "Không tìm thấy giao dịch chuyển khoản")
    valid_order_status = order.status == order_status or (
        action == "refund" and order.status == "DELIVERY_FAILED"
    )
    if not valid_order_status or payment.status not in (before, after):
        raise HTTPException(409, "Trạng thái giao dịch không cho phép thao tác này")
    if payment.status != after:
        payment.status = after
        db.commit()

    return {"payment_status": after}


@app.post("/api/v1/orders/{order_id}/delivery-failed")
def report_delivery_failure(
    order_id: str,
    reason: str = Body(..., embed=True, min_length=1, max_length=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_role(user, "DRIVER")
    reason = reason.strip()
    if not reason:
        raise HTTPException(422, "Vui lòng nhập lý do giao thất bại")

    order = lock_order(db, order_id)
    sub = find_sub_order(db, order.id)
    if sub is None:
        raise HTTPException(404, "Không tìm thấy chuyến giao")

    assignment = db.query(DeliveryAssignment).filter_by(
        sub_order_id=sub.id,
        driver_id=user.id,
        status="ACCEPTED",
    ).with_for_update().first()
    if assignment is None:
        raise HTTPException(404, "Không tìm thấy chuyến đang giao của bạn")

    if order.status != "DELIVERING" or sub.status != "DELIVERING":
        raise HTTPException(409, "Chỉ có thể báo thất bại khi đơn đang giao")

    payment = db.query(Payment).filter_by(order_id=order.id).first()
    if payment and payment.method == "ONLINE" and payment.status == "SUCCESS":
        payment.status = "REFUND_REVIEW"

    order.status = "DELIVERY_FAILED"
    sub.status = "DELIVERY_FAILED"
    assignment.status = "FAILED"
    db.add(DeliveryFailure(order_id=order.id, reason=reason))
    db.commit()

    return {"message": "Đã ghi nhận giao thất bại"}


@app.post("/api/v1/orders/{order_id}/failure-refund/{decision}")
def decide_failure_refund(
    order_id: str,
    decision: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_role(user, "ADMIN")
    decisions = {"approve": "REFUND_PROCESSING", "deny": "REFUND_DENIED"}
    if decision not in decisions:
        raise HTTPException(422, "Quyết định không hợp lệ")

    order = lock_order(db, order_id)
    payment = db.query(Payment).filter_by(order_id=order.id, method="ONLINE").first()
    if order.status != "DELIVERY_FAILED" or payment is None:
        raise HTTPException(409, "Đơn không thuộc diện duyệt hoàn tiền giao thất bại")

    target = decisions[decision]
    if payment.status == target:
        return {"payment_status": target}
    if payment.status != "REFUND_REVIEW":
        raise HTTPException(409, "Yêu cầu hoàn tiền đã được xử lý")

    payment.status = target
    db.commit()
    return {"payment_status": target}
