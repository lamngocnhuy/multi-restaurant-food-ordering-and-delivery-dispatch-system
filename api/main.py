import os
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from database.connection import engine, Base, get_db, SessionLocal
from models.entities import (
    User, Restaurant, FoodItem, Cart, CartItem,
    Order, SubOrder, OrderItem, DeliveryAssignment, Payment
)
from forms.schemas import AddToCartForm, CheckoutForm
from services.dispatch_service import run_auto_dispatch_loop, trigger_refund_if_paid_online

# Tự động khởi tạo 10 bảng CSDL nếu chưa tồn tại
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Multi-Restaurant Food Ordering & Delivery Dispatch System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.isdir("asset"):
    app.mount("/static", StaticFiles(directory="asset"), name="static")

# 0. Phục vụ giao diện Web chính
@app.get("/")
def serve_web_app():
    if os.path.exists("controls/index.html"):
        return FileResponse("controls/index.html")
    return {"message": "Backend API đang hoạt động! Truy cập /docs để xem tài liệu API."}

# 1. Khởi tạo dữ liệu mẫu để chạy thử hệ thống
@app.post("/api/v1/seed")
def seed_sample_data(db: Session = Depends(get_db)):
    if db.query(User).first():
        cust = db.query(User).filter(User.role == "CUSTOMER").first()
        drv = db.query(User).filter(User.role == "DRIVER").first()
        return {"message": "Dữ liệu đã sẵn sàng", "customer_id": cust.id, "driver_id": drv.id}

    cust = User(role="CUSTOMER", full_name="Nguyễn Văn A", email="khach1@gmail.com", password_hash="hashed_pass")
    owner1 = User(role="RESTAURANT", full_name="Chủ Quán Phở Hà Nội", email="pho@gmail.com", password_hash="hashed_pass")
    owner2 = User(role="RESTAURANT", full_name="Chủ Quán Cơm Tấm Sài Gòn", email="comtam@gmail.com", password_hash="hashed_pass")
    drv1 = User(role="DRIVER", full_name="Tài xế Trần Văn B", email="driver1@gmail.com", password_hash="hashed_pass", is_online=True)
    drv2 = User(role="DRIVER", full_name="Tài xế Lê Văn C", email="driver2@gmail.com", password_hash="hashed_pass", is_online=True)
    db.add_all([cust, owner1, owner2, drv1, drv2])
    db.commit()

    r1 = Restaurant(owner_id=owner1.id, name="Phở Bò Gia Truyền Hà Nội", address="19 Nguyễn Hữu Thọ, Q.7")
    r2 = Restaurant(owner_id=owner2.id, name="Cơm Tấm Sườn Bì Chả", address="45 Lê Văn Lương, Q.7")
    db.add_all([r1, r2])
    db.commit()

    foods = [
        FoodItem(restaurant_id=r1.id, name="Phở Bò Tái Nạm", price=45000),
        FoodItem(restaurant_id=r1.id, name="Phở Đặc Biệt Bát Đá", price=65000),
        FoodItem(restaurant_id=r2.id, name="Cơm Tấm Sườn Cốt Lết", price=40000),
        FoodItem(restaurant_id=r2.id, name="Cơm Tấm Sườn Bì Chả Trứng", price=55000),
    ]
    db.add_all(foods)
    db.commit()
    return {"message": "Khởi tạo dữ liệu thành công", "customer_id": cust.id, "driver_id": drv1.id}

# 2. Tra cứu thực đơn & Tìm kiếm (DT-MENU-01, DT-MENU-02)
@app.get("/api/v1/menu")
def get_menu(keyword: str = "", db: Session = Depends(get_db)):
    query = db.query(FoodItem, Restaurant).join(Restaurant, FoodItem.restaurant_id == Restaurant.id)
    if keyword:
        query = query.filter(FoodItem.name.ilike(f"%{keyword}%"))
    return [
        {
            "id": food.id,
            "name": food.name,
            "price": food.price,
            "status": food.status,
            "image_url": food.image_url,
            "restaurant_id": rest.id,
            "restaurant_name": rest.name
        }
        for food, rest in query.all()
    ]

# 3. Quản lý Giỏ hàng & Kiểm tra ràng buộc REQ-9 (DT-MENU-03)
@app.post("/api/v1/cart/items")
def add_to_cart(form: AddToCartForm, db: Session = Depends(get_db)):
    food = db.query(FoodItem).filter(FoodItem.id == form.food_id).first()
    if not food:
        raise HTTPException(status_code=404, detail="Món ăn không tồn tại")

    # Kiểm tra đầu vào (BVA): số lượng 1-99, phụ phí không âm
    if form.quantity < 1 or form.quantity > 99:
        raise HTTPException(status_code=400, detail="Số lượng phải từ 1 đến 99")
    if form.size_extra < 0 or form.topping_extra < 0:
        raise HTTPException(status_code=400, detail="Phụ phí không hợp lệ")

    cart = db.query(Cart).filter(Cart.customer_id == form.customer_id).first()
    if not cart:
        cart = Cart(customer_id=form.customer_id, restaurant_id=food.restaurant_id, total_amount=0)
        db.add(cart)
        db.commit()
        db.refresh(cart)

    # Kiểm tra quy tắc REQ-9: Chỉ cho phép đặt món tại 01 nhà hàng duy nhất
    if cart.restaurant_id and cart.restaurant_id != food.restaurant_id:
        existing_items = db.query(CartItem).filter(CartItem.cart_id == cart.id).count()
        if existing_items > 0 and not form.force_reset_cart:
            raise HTTPException(
                status_code=409,
                detail="REQ-9_CONFLICT: Giỏ hàng đang chứa món từ nhà hàng khác."
            )
        db.query(CartItem).filter(CartItem.cart_id == cart.id).delete()
        cart.restaurant_id = food.restaurant_id

    cart.restaurant_id = food.restaurant_id
    final_unit_price = food.price + form.size_extra + form.topping_extra

    item = db.query(CartItem).filter(CartItem.cart_id == cart.id, CartItem.food_id == food.id).first()
    if item:
        item.quantity += form.quantity
        item.unit_price = final_unit_price
        item.options_note = form.options_note
    else:
        db.add(CartItem(
            cart_id=cart.id,
            food_id=food.id,
            quantity=form.quantity,
            unit_price=final_unit_price,
            options_note=form.options_note
        ))
    db.commit()

    all_items = db.query(CartItem).filter(CartItem.cart_id == cart.id).all()
    cart.total_amount = sum(i.quantity * i.unit_price for i in all_items)
    db.commit()
    return {"message": "Đã thêm vào giỏ hàng", "total_amount": cart.total_amount}

@app.get("/api/v1/cart/{customer_id}")
def get_cart(customer_id: str, db: Session = Depends(get_db)):
    cart = db.query(Cart).filter(Cart.customer_id == customer_id).first()
    if not cart:
        return {"items": [], "total_amount": 0}
    items = db.query(CartItem, FoodItem).join(FoodItem, CartItem.food_id == FoodItem.id).filter(CartItem.cart_id == cart.id).all()
    return {
        "cart_id": cart.id,
        "restaurant_id": cart.restaurant_id,
        "total_amount": cart.total_amount,
        "items": [
            {
                "id": ci.id,
                "food_name": fi.name,
                "quantity": ci.quantity,
                "unit_price": ci.unit_price,
                "options_note": ci.options_note
            } for ci, fi in items
        ]
    }

# 4. Đặt hàng (Checkout) & Tách SubOrder (BR08, DT-ORD-01, DT-ORD-02)
@app.post("/api/v1/orders/checkout")
def checkout(form: CheckoutForm, db: Session = Depends(get_db)):
    # Kiểm tra đầu vào
    if not form.delivery_address or not form.delivery_address.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập đầy đủ thông tin giao hàng")
    if form.payment_method not in ("COD", "ONLINE"):
        raise HTTPException(status_code=400, detail="Phương thức thanh toán không hợp lệ")

    cart = db.query(Cart).filter(Cart.customer_id == form.customer_id).first()
    if not cart or not cart.restaurant_id:
        raise HTTPException(status_code=400, detail="Giỏ hàng trống")

    cart_items = db.query(CartItem).filter(CartItem.cart_id == cart.id).all()
    if not cart_items:
        raise HTTPException(status_code=400, detail="Giỏ hàng trống")

    delivery_fee = 15000.0
    grand_total = cart.total_amount + delivery_fee

    order = Order(
        customer_id=form.customer_id,
        delivery_address=form.delivery_address,
        grand_total=grand_total,
        status="PENDING"
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    sub_order = SubOrder(
        order_id=order.id,
        restaurant_id=cart.restaurant_id,
        subtotal=cart.total_amount,
        status="PENDING"
    )
    db.add(sub_order)
    db.commit()
    db.refresh(sub_order)

    for ci in cart_items:
        db.add(OrderItem(
            sub_order_id=sub_order.id,
            food_id=ci.food_id,
            quantity=ci.quantity,
            unit_price=ci.unit_price,
            total_price=ci.quantity * ci.unit_price
        ))

    db.add(Payment(
        order_id=order.id,
        method=form.payment_method,
        amount=grand_total,
        status="SUCCESS" if form.payment_method == "ONLINE" else "PENDING"
    ))

    db.query(CartItem).filter(CartItem.cart_id == cart.id).delete()
    cart.restaurant_id = None
    cart.total_amount = 0
    db.commit()

    return {"message": "Đặt hàng thành công", "order_id": order.id, "sub_order_id": sub_order.id}

# 5. Quản lý Đơn hàng, Xác nhận Bếp & Hủy đơn (BR10, ST-09)
@app.get("/api/v1/orders")
def list_all_orders(customer_id: str = None, db: Session = Depends(get_db)):
    query = db.query(Order).order_by(Order.created_at.desc())
    # Giao diện Khách nên truyền customer_id để chỉ thấy đơn của mình
    if customer_id:
        query = query.filter(Order.customer_id == customer_id)
    output = []
    for o in query.all():
        sub = db.query(SubOrder).filter(SubOrder.order_id == o.id).first()
        pay = db.query(Payment).filter(Payment.order_id == o.id).first()
        assign = db.query(DeliveryAssignment).filter(
            DeliveryAssignment.sub_order_id == (sub.id if sub else ""),
            DeliveryAssignment.status.in_(["OFFERED", "ACCEPTED", "COMPLETED"])
        ).first()
        output.append({
            "order_id": o.id,
            "sub_order_id": sub.id if sub else None,
            "delivery_address": o.delivery_address,
            "grand_total": o.grand_total,
            "status": o.status,
            "dispatch_status": getattr(sub, "dispatch_status", None) if sub else None,
            "payment_method": pay.method if pay else "COD",
            "payment_status": pay.status if pay else "PENDING",
            "assignment_id": assign.id if assign else None,
            "assignment_status": assign.status if assign else "NONE"
        })
    return output

@app.post("/api/v1/orders/{order_id}/restaurant-accept")
def restaurant_accept_order(order_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    sub = db.query(SubOrder).filter(SubOrder.order_id == order_id).first()
    if not order or not sub:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
    # Chỉ nhận đơn đang chờ xác nhận (tránh nhận đơn đã hủy / bấm 2 lần)
    if order.status != "PENDING":
        raise HTTPException(status_code=400, detail="Đơn hàng không ở trạng thái chờ xác nhận")
    order.status = "PREPARING"
    sub.status = "PREPARING"
    sub.dispatch_status = "SEARCHING"
    db.commit()

    background_tasks.add_task(run_auto_dispatch_loop, sub.id, SessionLocal)
    return {"message": "Nhà hàng đã xác nhận. Hệ thống đang điều phối tài xế!"}

@app.post("/api/v1/orders/{order_id}/cancel")
def cancel_order(order_id: str, role: str = "CUSTOMER", db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")

    # Đơn đã kết thúc thì không hủy lại (tránh hoàn tiền lặp)
    if order.status in ("CANCELLED", "COMPLETED"):
        raise HTTPException(status_code=400, detail="Đơn hàng đã kết thúc, không thể hủy")

    if role == "CUSTOMER" and order.status != "PENDING":
        raise HTTPException(status_code=400, detail="Không thể hủy đơn hàng khi nhà hàng đã tiếp nhận chế biến (BR10)!")

    order.status = "CANCELLED"

    # Đồng bộ trạng thái SubOrder để vòng lặp điều phối tự dừng
    sub = db.query(SubOrder).filter(SubOrder.order_id == order.id).first()
    if sub:
        sub.status = "CANCELLED"
        # Thu hồi các đề nghị đang chờ tài xế
        db.query(DeliveryAssignment).filter(
            DeliveryAssignment.sub_order_id == sub.id,
            DeliveryAssignment.status == "OFFERED"
        ).update({"status": "CANCELLED"})

    refunded = trigger_refund_if_paid_online(db, order.id)
    db.commit()
    return {
        "message": "Đã hủy đơn hàng" + (" và kích hoạt quy trình hoàn tiền ST-09." if refunded else "."),
        "refund_triggered": refunded
    }

# 6. Tài xế nhận / từ chối đơn, tìm lại tài xế & Hoàn tất giao hàng
@app.post("/api/v1/dispatch/{assignment_id}/accept")
def driver_accept_trip(assignment_id: str, db: Session = Depends(get_db)):
    assign = db.query(DeliveryAssignment).filter(DeliveryAssignment.id == assignment_id).first()
    if not assign or assign.status != "OFFERED":
        raise HTTPException(status_code=400, detail="Đề nghị giao hàng đã hết hạn hoặc không tồn tại")

    sub = db.query(SubOrder).filter(SubOrder.id == assign.sub_order_id).first()
    # Đơn đã bị hủy giữa chừng thì không được nhận
    if not sub or sub.status not in ("PREPARING", "READY"):
        raise HTTPException(status_code=400, detail="Đơn hàng đã bị hủy hoặc không còn cần giao")
    order = db.query(Order).filter(Order.id == sub.order_id).first()

    assign.status = "ACCEPTED"
    sub.status = "DELIVERING"
    order.status = "DELIVERING"
    db.commit()
    return {"message": "Tài xế đã nhận chuyến và đang giao hàng!"}

@app.post("/api/v1/dispatch/{assignment_id}/reject")
def driver_reject_trip(assignment_id: str, db: Session = Depends(get_db)):
    assign = db.query(DeliveryAssignment).filter(DeliveryAssignment.id == assignment_id).first()
    if not assign or assign.status != "OFFERED":
        raise HTTPException(status_code=400, detail="Đề nghị giao hàng đã hết hạn hoặc không tồn tại")
    assign.status = "REJECTED"
    db.commit()
    return {"message": "Tài xế đã từ chối chuyến, hệ thống chuyển cho tài xế khác."}

# DT-DRV-04: Khách chọn "Tiếp tục tìm tài xế" sau khi báo thiếu tài xế
@app.post("/api/v1/orders/{order_id}/retry-dispatch")
def retry_dispatch(order_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    sub = db.query(SubOrder).filter(SubOrder.order_id == order_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
    if sub.status not in ("PREPARING", "READY") or sub.dispatch_status != "FAILED":
        raise HTTPException(status_code=400, detail="Đơn hàng không ở trạng thái thiếu tài xế")
    # Đặt SEARCHING trước để chặn bấm nhiều lần tạo nhiều vòng lặp
    sub.dispatch_status = "SEARCHING"
    db.commit()
    background_tasks.add_task(run_auto_dispatch_loop, sub.id, SessionLocal)
    return {"message": "Hệ thống đang quét lại tài xế!"}

@app.post("/api/v1/orders/{order_id}/complete")
def complete_delivery(order_id: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn")
    # Chỉ hoàn tất đơn đang giao
    if order.status != "DELIVERING":
        raise HTTPException(status_code=400, detail="Chỉ hoàn tất được đơn đang giao")

    pay = db.query(Payment).filter(Payment.order_id == order_id).first()
    sub = db.query(SubOrder).filter(SubOrder.order_id == order_id).first()

    order.status = "COMPLETED"
    if sub:
        sub.status = "COMPLETED"
        # Giải phóng tài xế để nhận đơn mới
        db.query(DeliveryAssignment).filter(
            DeliveryAssignment.sub_order_id == sub.id,
            DeliveryAssignment.status == "ACCEPTED"
        ).update({"status": "COMPLETED"})
    if pay:
        pay.status = "SUCCESS"
    db.commit()
    return {"message": "Giao hàng hoàn tất & Đã đối soát thanh toán!"}