"""Business acceptance tests derived from FR01-15 and QD1-7 of the lab report."""
from uuid import uuid4
from datetime import timedelta
import hashlib
import hmac
import json
import pytest
from sqlalchemy import select, func
from models.entities import MenuItem, Restaurant, User, Driver, Order, Trip, now

ADDRESS = {'address':'19 Nguyen Hue, District 1, Ho Chi Minh City', 'lat':10.7769, 'lng':106.7009}

def ok(response, expected=None):
    assert response.status_code in ((expected,) if expected is not None else (200,201)), response.text
    return response.json()

def login(api, role='customer', email=None):
    result=ok(api.post('/api/auth/login',json={'email':email or f'{role}@localtable.vn','password':'Demo123!'}))
    assert result['user']['role'] == role
    return result['user']

def add(api, dish, **extra):
    return ok(api.post('/api/cart/items',json={'menu_item_id':dish.id,'quantity':1,**extra}))

def dishes(db, count=2):
    result=[]
    for restaurant in db.scalars(select(Restaurant).where(Restaurant.accepting_orders.is_(True)).order_by(Restaurant.id)):
        dish=db.scalar(select(MenuItem).where(MenuItem.restaurant_id==restaurant.id, MenuItem.available.is_(True)).order_by(MenuItem.id))
        if dish:result.append(dish)
        if len(result)==count:break
    assert len(result)==count
    return result

def place(api, payment='cod', **extra):
    return ok(api.post('/api/orders',json={**ADDRESS,'phone':'0901234567','payment_method':payment,'idempotency_key':str(uuid4()),**extra}))

def accept_all(api, db, order, ready=True):
    for sub in order['suborders']:
        owner=db.get(User,db.get(Restaurant,sub['restaurant_id']).owner_id)
        login(api,'restaurant',owner.email)
        for status in (['accepted','preparing','ready'] if ready else ['accepted']):
            result=ok(api.post(f"/api/restaurant/suborders/{sub['id']}/status",json={'status':status}))
    login(api)
    return ok(api.get('/api/orders/'+order['id']))['order']

def finish(api, db, order, cod=True):
    # Refresh location to ensure a GPS-valid driver is available for dispatch.
    for driver in db.scalars(select(Driver)):
        driver.last_location_at=now()
    db.commit()
    order=accept_all(api, db, order)
    assert order['trip'], order
    driver=db.get(Driver, db.get(Trip, order['trip']['id']).driver_id)
    login(api,'driver',driver.user.email)
    order=ok(api.post(f"/api/driver/trips/{order['trip']['id']}/accept",json={}))['order']
    for stop in order['trip']['pickups']:
        ok(api.post(f"/api/driver/trips/{order['trip']['id']}/pickup",json={'suborder_id':stop['suborder_id']}))
    return ok(api.post(f"/api/driver/trips/{order['trip']['id']}/complete",json={'cod_received':cod}))['order']

def test_catalog_details_and_search(api,db):
    catalog=ok(api.get('/api/restaurants'))['restaurants']
    assert len(catalog)>=4
    data=ok(api.get('/api/restaurants/'+catalog[0]['id']))
    assert data['menu'] and all(item['price']>0 for item in data['menu'])
    name=data['menu'][0]['name']
    found=ok(api.get('/api/menu',params={'q':name}))['items']
    assert any(item['name']==name for item in found)

def test_authentication_role_scoping_and_registration(api):
    assert api.get('/api/admin/dashboard').status_code==401
    login(api)
    assert api.get('/api/admin/dashboard').status_code==403
    assert api.get('/api/reports').status_code==403
    assert api.get('/api/restaurant/dashboard').status_code==403
    assert api.get('/api/driver/dashboard').status_code==403
    evil=api.post('/api/auth/register',json={'name':'Test User','email':'test@example.com','password':'Password123','role':'admin'})
    assert evil.status_code==422
    user=ok(api.post('/api/auth/register',json={'name':'Test User','email':'test@example.com','password':'Password123'}))['user']
    assert user['role']=='customer'
    assert api.post('/api/auth/login',json={'email':user['email'],'password':'incorrect'}).status_code==401

def test_customization_rejects_unknown_options_and_quantity(api,db):
    login(api);dish=dishes(db,1)[0]
    assert api.post('/api/cart/items',json={'menu_item_id':dish.id,'quantity':0}).status_code==422
    assert api.post('/api/cart/items',json={'menu_item_id':dish.id,'quantity':1.5}).status_code==422
    assert api.post('/api/cart/items',json={'menu_item_id':dish.id,'quantity':1,'options':{'toppings':['unoffered topping']}}).status_code==400
    assert api.post('/api/cart/items',json={'menu_item_id':dish.id,'quantity':1,'note':'x'*301}).status_code==422

def test_cart_quote_splits_restaurants_and_allocates_discount_exactly(api,db):
    login(api);selected=dishes(db)
    for dish in selected:add(api,dish,quantity=2)
    cart=ok(api.get('/api/cart')); assert len(cart['groups'])==2
    quote=ok(api.post('/api/cart/quote',json={**ADDRESS,'promo_code':'WELCOME10'}))
    assert quote['subtotal']==sum(g['subtotal'] for g in quote['groups'])
    assert quote['discount']==min(quote['subtotal']//10,50000)
    assert quote['total']==sum(g['total'] for g in quote['groups'])
    order=place(api,promo_code='WELCOME10')['order']
    assert len(order['suborders'])==2
    assert order['total']==quote['total']==sum(s['total'] for s in order['suborders'])
    assert ok(api.get('/api/cart'))['item_count']==0

def test_checkout_reprices_and_revalidates_availability(api,db):
    login(api);dish=dishes(db,1)[0];add(api,dish)
    dish.price+=17000; db.commit()
    quote=ok(api.post('/api/cart/quote',json=ADDRESS)); assert quote['subtotal']>=dish.price
    dish.available=False; db.commit()
    before=db.scalar(select(func.count()).select_from(Order))
    result=api.post('/api/orders',json={**ADDRESS,'phone':'0901234567','payment_method':'cod','idempotency_key':str(uuid4())})
    assert result.status_code==400 and 'sold out' in result.text.lower()
    assert db.scalar(select(func.count()).select_from(Order))==before
    assert ok(api.get('/api/cart'))['item_count']==1

def test_closed_restaurant_and_far_apart_group_are_rejected(api,db):
    login(api);a,b=dishes(db);add(api,a);add(api,b)
    a.restaurant.accepting_orders=False;db.commit()
    assert api.post('/api/cart/quote',json=ADDRESS).status_code==400
    a.restaurant.accepting_orders=True;b.restaurant.lat=20.0;db.commit()
    response=api.post('/api/cart/quote',json=ADDRESS)
    assert response.status_code==400 and ('apart' in response.text or 'separate' in response.text)

def test_idempotent_checkout_does_not_duplicate_or_clear_new_cart(api,db):
    login(api);dish=dishes(db,1)[0];add(api,dish)
    key=str(uuid4());body={**ADDRESS,'phone':'0901234567','payment_method':'cod','idempotency_key':key}
    first=ok(api.post('/api/orders',json=body))['order'];add(api,dish)
    second=ok(api.post('/api/orders',json=body))['order']
    assert first['id']==second['id']
    assert db.scalar(select(func.count()).select_from(Order).where(Order.idempotency_key==key))==1
    assert ok(api.get('/api/cart'))['item_count']==1

def test_online_payment_failure_retry_success_and_replay(api,db):
    login(api);add(api,dishes(db,1)[0])
    created=place(api,'online');o=created['order'];assert o['status']=='awaiting_payment'
    payment_id=created['payment_url'].rsplit('/',1)[-1]
    failed=ok(api.post(f'/api/payments/{payment_id}/sandbox',json={'outcome':'failure'}))['order']
    assert failed['payment_status']=='failed'
    retry=ok(api.post(f"/api/orders/{o['id']}/retry-payment",json={}))
    new_id=retry['payment_url'].rsplit('/',1)[-1];assert new_id!=payment_id
    paid=ok(api.post(f'/api/payments/{new_id}/sandbox',json={'outcome':'success'}))['order']
    assert paid['payment_status']=='paid' and paid['status']=='pending'
    again=ok(api.post(f'/api/payments/{new_id}/sandbox',json={'outcome':'success'}))['order']
    assert again['id']==paid['id'] and again['refund_amount']==0
    assert api.post(f'/api/payments/{new_id}/sandbox',json={'outcome':'failure'}).status_code==409

def test_partial_rejection_only_refunds_rejected_suborder(api,db):
    login(api)
    for dish in dishes(db):add(api,dish)
    created=place(api,'online');o=created['order'];pid=created['payment_url'].rsplit('/',1)[-1]
    ok(api.post(f'/api/payments/{pid}/sandbox',json={'outcome':'success'}))
    rejected=o['suborders'][0];owner=db.get(User,db.get(Restaurant,rejected['restaurant_id']).owner_id)
    login(api,'restaurant',owner.email)
    ok(api.post(f"/api/restaurant/suborders/{rejected['id']}/status",json={'status':'rejected','reason':'Kitchen closed'}))
    login(api)
    updated=ok(api.get('/api/orders/'+o['id']))['order']
    assert updated['refund_amount']==rejected['total']
    assert updated['payment_status']=='partially_refunded'
    assert sum(refund['amount'] for refund in updated['refunds'])==rejected['total']
    assert updated['payable_total']==o['total']-rejected['total']
    assert len([s for s in updated['suborders'] if s['status']=='pending'])==1
    login(api,'restaurant',owner.email)
    response=api.post(f"/api/restaurant/suborders/{rejected['id']}/status",json={'status':'rejected','reason':'again'})
    assert response.status_code in (200,409)
    if response.status_code==200: assert response.json()['order']['refund_amount']==rejected['total']

def test_delivery_requires_ordered_ready_pickups_and_cod_confirmation(api,db):
    login(api)
    for dish in dishes(db):add(api,dish)
    o=place(api)['order']
    for driver in db.scalars(select(Driver)):driver.last_location_at=now()
    db.commit();o=accept_all(api,db,o,ready=False);trip=o['trip'];assert trip
    driver=db.get(Driver,db.get(Trip,trip['id']).driver_id);login(api,'driver',driver.user.email)
    ok(api.post(f"/api/driver/trips/{trip['id']}/accept",json={}))
    assert api.post(f"/api/driver/trips/{trip['id']}/pickup",json={'suborder_id':trip['pickups'][0]['suborder_id']}).status_code==409
    assert api.post(f"/api/driver/trips/{trip['id']}/complete",json={'cod_received':True}).status_code==409
    for sub in o['suborders']:
        owner=db.get(User,db.get(Restaurant,sub['restaurant_id']).owner_id);login(api,'restaurant',owner.email)
        ok(api.post(f"/api/restaurant/suborders/{sub['id']}/status",json={'status':'preparing'}))
        ok(api.post(f"/api/restaurant/suborders/{sub['id']}/status",json={'status':'ready'}))
    login(api,'driver',driver.user.email)
    assert api.post(f"/api/driver/trips/{trip['id']}/pickup",json={'suborder_id':trip['pickups'][1]['suborder_id']}).status_code==409
    for stop in trip['pickups']:ok(api.post(f"/api/driver/trips/{trip['id']}/pickup",json={'suborder_id':stop['suborder_id']}))
    assert api.post(f"/api/driver/trips/{trip['id']}/complete",json={'cod_received':False}).status_code in (400,409)
    delivered=ok(api.post(f"/api/driver/trips/{trip['id']}/complete",json={'cod_received':True}))['order']
    assert delivered['status']=='delivered' and delivered['trip']['cod_collected']==delivered['payable_total']
    assert all(s['status']=='delivered' for s in delivered['suborders'])
    assert api.post(f"/api/driver/trips/{trip['id']}/complete",json={'cod_received':True}).status_code in (200,409)

def test_driver_decline_reassigns_to_different_driver(api,db):
    login(api);add(api,dishes(db,1)[0]);o=place(api)['order']
    for d in db.scalars(select(Driver)): d.online=True;d.available=True;d.last_location_at=now()
    db.commit();o=accept_all(api,db,o);trip=o['trip'];first=db.get(Trip,trip['id']).driver_id
    login(api,'driver',db.get(User,first).email)
    updated=ok(api.post(f"/api/driver/trips/{trip['id']}/decline",json={'reason':'Unavailable'}))['order']
    assert updated['trip'] and db.get(Trip,trip['id']).driver_id!=first
    assert db.get(Driver,first).available
    assert api.post(f"/api/driver/trips/{trip['id']}/accept",json={}).status_code in (403,404)

def test_customer_order_ownership_and_review_rules(api,db):
    login(api);add(api,dishes(db,1)[0]);o=place(api)['order']
    assert api.post(f"/api/orders/{o['id']}/reviews",json={'target_type':'restaurant','target_id':o['suborders'][0]['restaurant_id'],'rating':5,'comment':'Great'}).status_code==409
    o=finish(api,db,o);login(api)
    body={'target_type':'restaurant','target_id':o['suborders'][0]['restaurant_id'],'rating':5,'comment':'Fresh and delicious'}
    assert api.post(f"/api/orders/{o['id']}/reviews",json=body).status_code in (200,201)
    assert api.post(f"/api/orders/{o['id']}/reviews",json=body).status_code==409
    assert api.post(f"/api/orders/{o['id']}/reviews",json={**body,'rating':0}).status_code==422
    ok(api.post('/api/auth/register',json={'name':'Another Customer','email':'another@example.com','password':'Password123'}))
    assert api.get(f"/api/orders/{o['id']}").status_code in (403,404)

def test_admin_settlement_is_idempotent_and_cod_wallet_can_be_negative(api,db):
    login(api);add(api,dishes(db,1)[0]);o=finish(api,db,place(api)['order'])
    login(api,'admin')
    first=ok(api.post('/api/admin/settlements/run',json={'include_current':True}))
    settlements=ok(api.get('/api/admin/settlements'))['settlements']
    assert settlements
    counts=len(settlements)
    ok(api.post('/api/admin/settlements/run',json={'include_current':True}))
    again=ok(api.get('/api/admin/settlements'))['settlements'];assert len(again)==counts
    driver=[s for s in settlements if s['party_type']=='driver' and s['party_id']==db.get(Trip,o['trip']['id']).driver_id]
    assert driver and driver[0]['amount']==driver[0]['gross_amount']-driver[0]['cod_collected']
    assert driver[0]['amount']<0
    closed=next(s for s in settlements if s['period_end']<now().isoformat())
    paid=ok(api.post(f"/api/admin/settlements/{closed['id']}/paid",json={}))['settlement'];assert paid['status']=='paid'
    report=ok(api.get('/api/reports'));assert report['summary']['completed_orders']>=1

def test_menu_validation_and_out_of_stock_preservation(api,db):
    login(api,'restaurant')
    body={'code':'TEST-NEW','name':'New dish','category':'Vietnamese','price':50000,'available':True}
    dish=ok(api.post('/api/restaurant/menu',json=body))['item']
    assert api.post('/api/restaurant/menu',json=body).status_code==409
    assert api.post('/api/restaurant/menu',json={**body,'code':'BAD','price':0}).status_code==422
    ok(api.patch('/api/restaurant/menu/'+dish['id'],json={'available':False}))
    assert api.delete('/api/restaurant/menu/'+dish['id']).status_code in (400,409)
    assert db.get(MenuItem,dish['id']) is not None

def test_gps_role_validation_and_active_account_enforcement(api,db):
    customer=login(api)
    assert api.post('/api/driver/location',json={'lat':10,'lng':106}).status_code==403
    driver=login(api,'driver')
    assert api.post('/api/driver/location',json={'lat':91,'lng':0}).status_code==422
    ok(api.post('/api/driver/location',json={'lat':10.776,'lng':106.70}))
    data=ok(api.get('/api/driver/dashboard'))['driver'];assert data['lat']==10.776 and data['last_location_at']
    login(api,'admin');ok(api.patch('/api/admin/users/'+customer['id'],json={'active':False}))
    assert api.post('/api/auth/login',json={'email':customer['email'],'password':'Demo123!'}).status_code in (401,403)
