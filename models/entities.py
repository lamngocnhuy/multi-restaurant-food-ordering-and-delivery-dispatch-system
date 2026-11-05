"""Persisted money is integer Vietnamese dong; order items are immutable snapshots."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, JSON, Text, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.connection import Base

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30), default='')
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (CheckConstraint("role IN ('customer','restaurant','driver','admin')", name='valid_role'),)

class Restaurant(Base):
    __tablename__ = 'restaurants'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), unique=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(80), index=True)
    image: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(String(250))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    accepting_orders: Mapped[bool] = mapped_column(Boolean, default=True)
    delivery_minutes: Mapped[int] = mapped_column(Integer, default=25)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    menu: Mapped[list['MenuItem']] = relationship(back_populates='restaurant')

class MenuItem(Base):
    __tablename__ = 'menu_items'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    restaurant_id: Mapped[str] = mapped_column(ForeignKey('restaurants.id'), index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(150), index=True)
    description: Mapped[str] = mapped_column(Text, default='')
    category: Mapped[str] = mapped_column(String(80), index=True)
    price: Mapped[int] = mapped_column(Integer)
    image: Mapped[str] = mapped_column(Text, default='')
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    popular: Mapped[bool] = mapped_column(Boolean, default=False)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    restaurant: Mapped[Restaurant] = relationship(back_populates='menu')
    __table_args__ = (UniqueConstraint('restaurant_id','code',name='uq_restaurant_dish_code'), CheckConstraint('price > 0', name='positive_price'))

class CartItem(Base):
    __tablename__ = 'cart_items'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    menu_item_id: Mapped[str] = mapped_column(ForeignKey('menu_items.id'))
    quantity: Mapped[int] = mapped_column(Integer)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(String(300), default='')
    menu_item: Mapped[MenuItem] = relationship()
    __table_args__ = (CheckConstraint('quantity > 0 AND quantity <= 99', name='cart_quantity'),)

class Order(Base):
    __tablename__ = 'orders'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default='pending', index=True)
    payment_method: Mapped[str] = mapped_column(String(20))
    payment_status: Mapped[str] = mapped_column(String(30), default='pending')
    subtotal: Mapped[int] = mapped_column(Integer)
    delivery_fee: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    refund_amount: Mapped[int] = mapped_column(Integer, default=0)
    address: Mapped[str] = mapped_column(String(300))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    phone: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(String(500), default='')
    promo_code: Mapped[str] = mapped_column(String(30), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customer: Mapped[User] = relationship()
    suborders: Mapped[list['SubOrder']] = relationship(back_populates='order', cascade='all, delete-orphan')
    events: Mapped[list['OrderEvent']] = relationship(order_by='OrderEvent.created_at', cascade='all, delete-orphan')
    reviews: Mapped[list['Review']] = relationship(cascade='all, delete-orphan')
    payments: Mapped[list['Payment']] = relationship(back_populates='order')
    refunds: Mapped[list['Refund']] = relationship()
    trip: Mapped['Trip | None'] = relationship(back_populates='order', uselist=False)
    __table_args__ = (UniqueConstraint('customer_id','idempotency_key',name='uq_order_idempotency'), CheckConstraint('total >= 0 AND refund_amount >= 0 AND refund_amount <= total',name='order_money'),)

class SubOrder(Base):
    __tablename__ = 'suborders'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    restaurant_id: Mapped[str] = mapped_column(ForeignKey('restaurants.id'), index=True)
    restaurant_name: Mapped[str] = mapped_column(String(150))
    address: Mapped[str] = mapped_column(String(300))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default='pending', index=True)
    subtotal: Mapped[int] = mapped_column(Integer)
    delivery_fee: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    order: Mapped[Order] = relationship(back_populates='suborders')
    items: Mapped[list['OrderItem']] = relationship(cascade='all, delete-orphan')
    __table_args__ = (UniqueConstraint('order_id','restaurant_id'), CheckConstraint('total >= 0', name='suborder_total'),)

class OrderItem(Base):
    __tablename__ = 'order_items'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    suborder_id: Mapped[str] = mapped_column(ForeignKey('suborders.id'), index=True)
    menu_item_id: Mapped[str] = mapped_column(ForeignKey('menu_items.id'))
    name: Mapped[str] = mapped_column(String(150))
    quantity: Mapped[int] = mapped_column(Integer)
    options: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(String(300))
    unit_price: Mapped[int] = mapped_column(Integer)
    line_total: Mapped[int] = mapped_column(Integer)

class Payment(Base):
    __tablename__ = 'payments'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    provider: Mapped[str] = mapped_column(String(30), default='sandbox')
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default='pending')
    external_reference: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    order: Mapped[Order] = relationship(back_populates='payments')

class Driver(Base):
    __tablename__ = 'drivers'
    id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    lat: Mapped[float] = mapped_column(Float, default=10.7769)
    lng: Mapped[float] = mapped_column(Float, default=106.7009)
    last_location_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    user: Mapped[User] = relationship()

class Trip(Base):
    __tablename__ = 'trips'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), unique=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey('drivers.id'), index=True)
    status: Mapped[str] = mapped_column(String(30), default='offered', index=True)
    pickups: Mapped[list] = mapped_column(JSON, default=list)
    declined_driver_ids: Mapped[list] = mapped_column(JSON, default=list)
    delivery_fee: Mapped[int] = mapped_column(Integer)
    cod_amount: Mapped[int] = mapped_column(Integer, default=0)
    cod_collected: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    driver: Mapped[Driver] = relationship()
    order: Mapped[Order] = relationship(back_populates='trip')

class OrderEvent(Base):
    __tablename__ = 'order_events'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    status: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Review(Base):
    __tablename__ = 'reviews'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(40), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint('order_id','target_type','target_id',name='uq_review_target'), CheckConstraint('rating BETWEEN 1 AND 5', name='review_rating'),)

class DispatchConfig(Base):
    __tablename__ = 'dispatch_config'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    max_group_distance_km: Mapped[float] = mapped_column(Float, default=5.0)
    dispatch_radius_km: Mapped[float] = mapped_column(Float, default=15.0)
    base_delivery_fee: Mapped[int] = mapped_column(Integer, default=12000)
    per_km_fee: Mapped[int] = mapped_column(Integer, default=4000)
    commission_rate: Mapped[float] = mapped_column(Float, default=0.10)

class Settlement(Base):
    __tablename__ = 'settlements'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    party_type: Mapped[str] = mapped_column(String(20))
    party_id: Mapped[str] = mapped_column(String(40))
    party_name: Mapped[str] = mapped_column(String(150))
    gross_amount: Mapped[int] = mapped_column(Integer)
    commission: Mapped[int] = mapped_column(Integer, default=0)
    cod_collected: Mapped[int] = mapped_column(Integer, default=0)
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint('period_start','party_type','party_id',name='uq_settlement_period_party'),)

class SettlementEntry(Base):
    __tablename__ = 'settlement_entries'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    settlement_id: Mapped[str] = mapped_column(ForeignKey('settlements.id'), index=True)
    source_type: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[str] = mapped_column(String(40))
    __table_args__ = (UniqueConstraint('source_type','source_id',name='uq_settlement_source'),)

class Refund(Base):
    """Sandbox refund ledger; a real provider must settle before marking refunded."""
    __tablename__ = 'refunds'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey('payments.id'))
    suborder_id: Mapped[str | None] = mapped_column(ForeignKey('suborders.id'), nullable=True, unique=True)
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default='refunded')
    reason: Mapped[str] = mapped_column(String(500))
    provider_reference: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (CheckConstraint('amount > 0',name='positive_refund'),)
