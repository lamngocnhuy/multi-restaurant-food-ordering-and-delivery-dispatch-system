"""PostgreSQL row-lock guarantees tested with independent concurrent transactions."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from database.connection import engine, SessionLocal
from models.entities import User, MenuItem, CartItem, Order, Payment
from forms.schemas import Checkout
from services.commerce import checkout

pytestmark = pytest.mark.skipif(engine.dialect.name != 'postgresql', reason='PostgreSQL concurrency acceptance; set TEST_DATABASE_URL ending in _test.')

def test_simultaneous_checkout_creates_one_invoice_and_one_payment(application):
    customer_id=str(uuid4());key=str(uuid4())
    with SessionLocal() as db:
        u=User(id=customer_id,email=customer_id+'@example.com',name='Concurrent customer',phone='0901234567',password_hash='unused-in-service-test',role='customer',active=True)
        db.add(u);db.flush()
        dish=db.scalar(select(MenuItem).where(MenuItem.available.is_(True)))
        db.add(CartItem(user_id=u.id,menu_item_id=dish.id,quantity=2,options={},note='Concurrent checkout'))
        db.commit()
    data=Checkout(address='19 Nguyen Hue, Ho Chi Minh City',lat=10.7769,lng=106.7009,phone='0901234567',payment_method='online',idempotency_key=key)
    def submit(_):
        with SessionLocal() as db:
            user=db.get(User,customer_id)
            order,payment=checkout(db,user,data)
            db.commit()
            return order.id,payment.id
    with ThreadPoolExecutor(max_workers=8) as executor:
        results=list(executor.map(submit,range(16)))
    assert len(set(results))==1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Order).where(Order.customer_id==customer_id))==1
        assert db.scalar(select(func.count()).select_from(Payment).where(Payment.order_id==results[0][0]))==1
        assert db.scalar(select(func.count()).select_from(CartItem).where(CartItem.user_id==customer_id))==0
