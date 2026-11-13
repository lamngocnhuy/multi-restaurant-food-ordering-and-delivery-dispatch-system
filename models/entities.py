import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, Boolean, ForeignKey, DateTime, Text, UniqueConstraint
from database.connection import Base

def gen_uuid():
    return str(uuid.uuid4())

# 1. Bảng Người dùng (4 vai trò: CUSTOMER, RESTAURANT, DRIVER, ADMIN)
class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=gen_uuid)
    role = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    status = Column(String, default="ACTIVE")   # ACTIVE, PENDING, LOCKED
    is_online = Column(Boolean, default=True)   # Trạng thái bật/tắt ca của Tài xế
    created_at = Column(DateTime, default=datetime.utcnow)

# 2. Bảng Nhà hàng đối tác
class Restaurant(Base):
    __tablename__ = "restaurants"
    id = Column(String, primary_key=True, default=gen_uuid)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    address = Column(Text, nullable=False)
    latitude = Column(Float, default=10.7326)
    longitude = Column(Float, default=106.6992)
    status = Column(String, default="OPEN")     # OPEN, CLOSED

# 3. Bảng Thực đơn món ăn
class FoodItem(Base):
    __tablename__ = "food_items"
    id = Column(String, primary_key=True, default=gen_uuid)
    restaurant_id = Column(String, ForeignKey("restaurants.id"), nullable=False)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    image_url = Column(String, default="https://images.unsplash.com/photo-1582878826629-29b7ad1cdc43?w=400")
    status = Column(String, default="IN_STOCK") # IN_STOCK, OUT_OF_STOCK

# 4. Bảng Giỏ hàng (Ràng buộc REQ-9: 1 khách tối đa 1 giỏ, gắn với 1 nhà hàng)
class Cart(Base):
    __tablename__ = "carts"
    id = Column(String, primary_key=True, default=gen_uuid)
    customer_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    restaurant_id = Column(String, ForeignKey("restaurants.id"), nullable=True)
    total_amount = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow)

# 5. Bảng Chi tiết món trong giỏ
class CartItem(Base):
    __tablename__ = "cart_items"
    id = Column(String, primary_key=True, default=gen_uuid)
    cart_id = Column(String, ForeignKey("carts.id"), nullable=False)
    food_id = Column(String, ForeignKey("food_items.id"), nullable=False)
    quantity = Column(Integer, default=1)
    unit_price = Column(Float, nullable=False)
    options_note = Column(Text, default="")
    __table_args__ = (UniqueConstraint("cart_id", "food_id", name="uq_cart_food"),)

# 6. Bảng Đơn hàng tổng
class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True, default=gen_uuid)
    customer_id = Column(String, ForeignKey("users.id"), nullable=False)
    delivery_address = Column(Text, nullable=False)
    grand_total = Column(Float, nullable=False)
    status = Column(String, default="PENDING")  # PENDING, PREPARING, READY, DELIVERING, COMPLETED, CANCELLED
    created_at = Column(DateTime, default=datetime.utcnow)

# 7. Bảng Đơn hàng con theo Nhà hàng
class SubOrder(Base):
    __tablename__ = "sub_orders"
    id = Column(String, primary_key=True, default=gen_uuid)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False)
    restaurant_id = Column(String, ForeignKey("restaurants.id"), nullable=False)
    subtotal = Column(Float, nullable=False)
    status = Column(String, default="PENDING")  # PENDING, PREPARING, READY, REJECTED, DELIVERING, COMPLETED
    __table_args__ = (UniqueConstraint("order_id", "restaurant_id", name="uq_order_restaurant"),)

# 8. Bảng Chi tiết món đã đặt (Lưu cố định giá tại thời điểm đặt - BR02)
class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(String, primary_key=True, default=gen_uuid)
    sub_order_id = Column(String, ForeignKey("sub_orders.id"), nullable=False)
    food_id = Column(String, ForeignKey("food_items.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)

# 9. Bảng Phân công & Điều phối Tài xế (ST-02)
class DeliveryAssignment(Base):
    __tablename__ = "delivery_assignments"
    id = Column(String, primary_key=True, default=gen_uuid)
    sub_order_id = Column(String, ForeignKey("sub_orders.id"), nullable=False)
    driver_id = Column(String, ForeignKey("users.id"), nullable=False)
    fee = Column(Float, default=15000.0)
    status = Column(String, default="OFFERED")  # OFFERED, ACCEPTED, REJECTED, TIMEOUT, COMPLETED
    assigned_at = Column(DateTime, default=datetime.utcnow)

# 10. Bảng Thanh toán & Hoàn tiền (ST-03 & ST-09)
class Payment(Base):
    __tablename__ = "payments"
    id = Column(String, primary_key=True, default=gen_uuid)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False)
    method = Column(String, nullable=False)     # COD, ONLINE
    amount = Column(Float, nullable=False)
    status = Column(String, default="PENDING")  # PENDING, SUCCESS, REFUND_PROCESSING, REFUNDED