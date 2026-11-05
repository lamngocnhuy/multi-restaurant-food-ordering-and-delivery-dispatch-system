"""Additional API boundary and financial edge-case acceptance checks."""
import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select
from models.entities import User, Driver, Restaurant, MenuItem, Payment, Trip, now
from services.reconciliation import period_for
from properties.config import PAYMENT_SECRET
from test_workflows import ok,login,add,dishes,place,finish,accept_all,ADDRESS


def test_admin_provisions_roles_without_public_self_elevation(api,db):
    login(api)
    body={'name':'New Driver','email':'newdriver@example.com','password':'Password123','phone':'0901234567','role':'driver'}
    assert api.post('/api/admin/users',json=body).status_code==403
    login(api,'admin');driver=ok(api.post('/api/admin/users',json=body))['user']
    assert driver['role']=='driver' and db.get(Driver,driver['id']) is not None
    assert api.post('/api/admin/users',json=body).status_code==409
    partner={**body,'name':'New Restaurant','email':'partner@example.com','role':'restaurant'}
    assert api.post('/api/admin/users',json=partner).status_code in (400,422)
    partner['restaurant']={'name':'Test Kitchen','category':'Vietnamese','description':'Fresh daily','address':'19 Nguyen Hue, District 1','lat':10.7769,'lng':106.7009,'image':''}
    user=ok(api.post('/api/admin/users',json=partner))['user']
    r=db.scalar(select(Restaurant).where(Restaurant.owner_id==user['id']));assert r and r.name=='Test Kitchen'


def test_session_cookie_and_cross_origin_mutations(api):
    response=api.post('/api/auth/login',json={'email':'customer@localtable.vn','password':'Demo123!'})
    ok(response);cookie=response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=lax' in cookie
    assert api.post('/api/auth/logout',headers={'Origin':'https://untrusted.example'}).status_code==403
    assert api.post('/api/auth/logout',headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
    assert ok(api.get('/api/auth/me'))['user']
    api.cookies.set('gather_session','modified.invalid')
    assert api.get('/api/cart').status_code==401


def test_payment_callbacks_require_signature_and_deduplicate_external_reference(api,db):
    login(api);add(api,dishes(db,1)[0]);created=place(api,'online')
    payment_id=created['payment_url'].rsplit('/',1)[-1]
    body=json.dumps({'payment_id':payment_id,'outcome':'success','external_reference':'provider-test-reference'}).encode()
    assert api.post('/api/payments/callback',content=body,headers={'Content-Type':'application/json'}).status_code==403
    signature=hmac.new(PAYMENT_SECRET.encode(),body,hashlib.sha256).hexdigest()
    headers={'Content-Type':'application/json','X-Payment-Signature':signature}
    order=ok(api.post('/api/payments/callback',content=body,headers=headers))['order']
    assert order['payment_status']=='paid'
    assert ok(api.post('/api/payments/callback',content=body,headers=headers))['order']['id']==order['id']
    add(api,dishes(db,1)[0]);second=place(api,'online');pid=second['payment_url'].rsplit('/',1)[-1]
    other=json.dumps({'payment_id':pid,'outcome':'success','external_reference':'provider-test-reference'}).encode()
    sig=hmac.new(PAYMENT_SECRET.encode(),other,hashlib.sha256).hexdigest()
    assert api.post('/api/payments/callback',content=other,headers={**headers,'X-Payment-Signature':sig}).status_code==409


def test_restaurant_cannot_read_or_change_other_restaurant_suborder(api,db):
    login(api)
    for dish in dishes(db):add(api,dish)
    order=place(api)['order'];sub=order['suborders'][0];owner=db.get(User,db.get(Restaurant,sub['restaurant_id']).owner_id)
    login(api,'restaurant',owner.email)
    scoped=ok(api.get('/api/orders/'+order['id']))['order']
    assert len(scoped['suborders'])==1
    assert scoped['total']==sub['total']
    other=next(s for s in order['suborders'] if s['id']!=sub['id'])
    assert api.post('/api/restaurant/suborders/'+other['id']+'/status',json={'status':'accepted'}).status_code==404


def test_incident_requires_admin_resolution_and_cannot_be_marked_delivered(api,db):
    login(api);add(api,dishes(db,1)[0]);o=place(api)['order']
    for driver in db.scalars(select(Driver)):driver.last_location_at=now()
    db.commit();o=accept_all(api,db,o);trip=o['trip'];driver=db.get(Trip,trip['id']).driver_id
    login(api,'driver',db.get(User,driver).email)
    ok(api.post('/api/driver/trips/'+trip['id']+'/accept',json={}))
    order=ok(api.post('/api/driver/trips/'+trip['id']+'/incident',json={'reason':'Customer cannot be reached'}))['order'];assert order['status']=='incident'
    assert api.post('/api/driver/trips/'+trip['id']+'/complete',json={'cod_received':True}).status_code==409
    login(api)
    assert api.post('/api/admin/orders/'+o['id']+'/resolve',json={'action':'cancel','reason':'Unreachable'}).status_code==403
    login(api,'admin')
    cancelled=ok(api.post('/api/admin/orders/'+o['id']+'/resolve',json={'action':'cancel','reason':'Confirmed unreachable customer'}))['order']
    assert cancelled['status']=='cancelled' and cancelled['payable_total']==0
    assert db.get(Driver,driver).available


def test_freeship_does_not_reduce_restaurant_food_revenue(api,db):
    login(api);dish=dishes(db,1)[0];add(api,dish)
    o=finish(api,db,place(api,promo_code='FREESHIP')['order'])
    sub=o['suborders'][0];owner=db.get(User,db.get(Restaurant,sub['restaurant_id']).owner_id)
    login(api,'restaurant',owner.email)
    dashboard=ok(api.get('/api/restaurant/dashboard'))
    assert dashboard['stats']['revenue_today']==sub['subtotal']
    report=ok(api.get('/api/reports'))['summary']
    # There may also be a seeded past order; this comparison covers all scoped sales.
    assert report['net_revenue']==report['food_revenue']-report.get('food_discounts',report['discounts'])-report['commission']


def test_weekly_cutoff_places_last_sunday_minute_in_next_period():
    before=datetime(2026,11,1,16,58,59,tzinfo=timezone.utc) # Sunday 23:58:59 Vietnam
    cutoff=datetime(2026,11,1,16,59,0,tzinfo=timezone.utc)
    after=cutoff+timedelta(seconds=30)
    a=period_for(before);b=period_for(after)
    assert a[1]==cutoff
    assert b[0]==cutoff and b[1]>after


def test_unanswered_driver_offer_expires_and_is_reassigned(api,db):
    from services.commerce import retry_waiting_dispatch
    login(api);add(api,dishes(db,1)[0]);o=place(api)['order']
    for driver in db.scalars(select(Driver)):
        driver.online=True;driver.available=True;driver.last_location_at=now()
    db.commit();o=accept_all(api,db,o)
    trip=db.get(Trip,o['trip']['id']);previous=trip.driver_id
    trip.created_at=now()-timedelta(seconds=100);db.commit()
    retry_waiting_dispatch(db);db.commit();db.refresh(trip)
    assert trip.status=='offered' and trip.driver_id!=previous
    assert previous in trip.declined_driver_ids and db.get(Driver,previous).available


def test_unpaid_online_order_is_hidden_from_restaurant_until_confirmation(api,db):
    login(api);dish=dishes(db,1)[0];add(api,dish);created=place(api,'online');o=created['order']
    owner=db.get(User,dish.restaurant.owner_id)
    login(api,'restaurant',owner.email)
    assert o['id'] not in {order['id'] for order in ok(api.get('/api/restaurant/dashboard'))['orders']}
    assert api.get('/api/orders/'+o['id']).status_code in (403,404)
    login(api);pid=created['payment_url'].rsplit('/',1)[-1]
    ok(api.post('/api/payments/'+pid+'/sandbox',json={'outcome':'success'}))
    login(api,'restaurant',owner.email)
    assert o['id'] in {order['id'] for order in ok(api.get('/api/restaurant/dashboard'))['orders']}
