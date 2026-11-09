"""Role-scoped JSON API. Business mutations run in one database transaction."""
from datetime import datetime, timezone, timedelta, date
from collections import Counter, defaultdict
import hashlib
import hmac
import logging
import threading
import time
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session, selectinload
from database.connection import get_db
from models.entities import *
from forms.schemas import *
from services.commerce import *
from services.reconciliation import reconcile, settlement_json, aware
from utilities.security import hash_password, check_password, token_for, read_token
from properties.config import COOKIE_SECURE, APP_ENV, SEED_DEMO, PAYMENT_PROVIDER, PAYMENT_SECRET

router=APIRouter(prefix='/api')
log=logging.getLogger('gather.security')
login_attempts={};attempts_lock=threading.Lock()

def current(request:Request,db:Session=Depends(get_db)):
    token=request.cookies.get('gather_session','');id_=read_token(token);u=db.get(User,id_) if id_ else None
    if not u or not u.active:
        log.warning('authentication_denied path=%s',request.url.path)
        raise HTTPException(401,'Please sign in to continue.')
    return u

def roles(*allowed):
    def dependency(request:Request,u:User=Depends(current)):
        if u.role not in allowed:
            log.warning('access_denied user=%s role=%s path=%s',u.id,u.role,request.url.path)
            raise HTTPException(403,'Your account does not have permission to perform this action.')
        return u
    return dependency
customer=roles('customer');restaurant_user=roles('restaurant');driver_user=roles('driver');admin=roles('admin');reporter=roles('restaurant','admin')

def owned_restaurant(db,u):
    r=db.scalar(select(Restaurant).where(Restaurant.owner_id==u.id))
    if not r:fail('Your restaurant profile has not been configured. Contact an administrator.',404)
    return r

def view_user(db,u):
    r=db.scalar(select(Restaurant.id).where(Restaurant.owner_id==u.id)) if u.role=='restaurant' else None
    return user_json(u,r)

def restaurant_visible(o):
    return o.payment_method=='cod' or o.payment_status in {'paid','partially_refunded','refunded'}

def restaurant_visibility():
    return (Order.payment_method=='cod') | Order.payment_status.in_(['paid','partially_refunded','refunded'])

def accessible(db,o,u):
    allowed=u.role=='admin' or (u.role=='customer' and o.customer_id==u.id) or (u.role=='driver' and o.trip and o.trip.driver_id==u.id) or (u.role=='restaurant' and restaurant_visible(o) and any(s.restaurant_id==owned_restaurant(db,u).id for s in o.suborders))
    if not allowed:
        log.warning('order_access_denied user=%s order=%s',u.id,o.id);fail('You do not have access to this order.',403)

def scoped_json(db,o,u):
    payload=order_json(o)
    if u.role=='restaurant':
        rid=owned_restaurant(db,u).id
        payload['suborders']=[s for s in payload['suborders'] if s['restaurant_id']==rid]
        own_suborder_ids={s['id'] for s in payload['suborders']}
        payload['refunds']=[r for r in payload['refunds'] if r['suborder_id'] in own_suborder_ids]
        for key in ('subtotal','delivery_fee','discount','total'):payload[key]=sum(s[key] for s in payload['suborders'])
        payload['refund_amount']=sum(s['total'] for s in payload['suborders'] if s['status'] in {'rejected','cancelled'})
        payload['payable_total']=payload['total']-payload['refund_amount']
        if payload['trip']:payload['trip']['pickups']=[p for p in payload['trip']['pickups'] if p['suborder_id'] in {s['id'] for s in payload['suborders']}]
        payload['events']=[e for e in payload['events'] if e['status'] not in {'rejected'} or owned_restaurant(db,u).name in e['message']]
    return payload

def cookie(response,u):response.set_cookie('gather_session',token_for(u.id),max_age=604800,httponly=True,secure=COOKIE_SECURE,samesite='lax',path='/')

@router.get('/auth/me')
def me(request:Request,db:Session=Depends(get_db)):
    id_=read_token(request.cookies.get('gather_session',''));u=db.get(User,id_) if id_ else None
    return {'user':view_user(db,u) if u and u.active else None,'demo_mode':SEED_DEMO and APP_ENV!='production'}

@router.post('/auth/register',status_code=201)
def register(data:Register,response:Response,db:Session=Depends(get_db)):
    if db.scalar(select(User).where(User.email==data.email.lower())):fail('This email is already registered. Sign in or choose another email.',409)
    u=User(name=data.name,email=data.email.lower(),phone=data.phone,password_hash=hash_password(data.password),role='customer',active=True);db.add(u);db.flush();cookie(response,u)
    return {'user':view_user(db,u)}

@router.post('/auth/login')
def login(data:Login,request:Request,response:Response,db:Session=Depends(get_db)):
    ip=request.client.host if request.client else 'unknown';key=(ip,data.email.lower());stamp=time.monotonic()
    with attempts_lock:
        old=[x for x in login_attempts.get(key,[]) if stamp-x<300]
        if len(old)>=15:fail('Too many sign-in attempts. Wait five minutes and try again.',429)
        login_attempts[key]=old+[stamp]
        if len(login_attempts)>10000:
            expired=[k for k,v in login_attempts.items() if not v or stamp-v[-1]>300]
            for k in expired:login_attempts.pop(k,None)
    u=db.scalar(select(User).where(User.email==data.email.lower()))
    if not u or not check_password(data.password,u.password_hash):fail('Email or password is incorrect. Check both and try again.',401)
    if not u.active:fail('This account is inactive. Contact an administrator.',403)
    with attempts_lock:login_attempts.pop(key,None)
    cookie(response,u);return {'user':view_user(db,u)}

@router.post('/auth/logout')
def logout(response:Response):response.delete_cookie('gather_session',path='/');return {'message':'Signed out.'}

@router.get('/config')
def public_config(db:Session=Depends(get_db)):
    c=config(db)
    return {'currency':'VND','city':'Ho Chi Minh City','default_location':{'lat':10.7769,'lng':106.7009},'max_group_distance_km':c.max_group_distance_km,'base_delivery_fee':c.base_delivery_fee,'per_km_fee':c.per_km_fee,'payment_provider':PAYMENT_PROVIDER,'sandbox_payment':PAYMENT_PROVIDER=='sandbox','promos':[{'code':'WELCOME10','description':'10% off food, up to 50,000₫'},{'code':'FREESHIP','description':'Up to 30,000₫ off delivery'}]}

@router.get('/restaurants', dependencies=[Depends(customer)])
def restaurants(q:str='',category:str='',db:Session=Depends(get_db)):
    stmt=select(Restaurant)
    if q:stmt=stmt.where(Restaurant.name.ilike(f'%{q[:100]}%')|Restaurant.description.ilike(f'%{q[:100]}%'))
    if category and category.lower() not in {'all','all cuisines'}:stmt=stmt.where(Restaurant.category.ilike(category[:80]))
    return {'restaurants':[restaurant_json(db,r) for r in db.scalars(stmt.order_by(Restaurant.featured.desc(),Restaurant.name))]}

@router.get('/restaurants/{rid}', dependencies=[Depends(customer)])
def restaurant_detail(rid:str,db:Session=Depends(get_db)):
    r=db.get(Restaurant,rid)
    if not r:fail('Restaurant was not found.',404)
    return {'restaurant':restaurant_json(db,r),'menu':[menu_json(m) for m in db.scalars(select(MenuItem).where(MenuItem.restaurant_id==rid).order_by(MenuItem.popular.desc(),MenuItem.category,MenuItem.name))]}

@router.get('/menu', dependencies=[Depends(customer)])
def menu(q:str='',category:str='',restaurant_id:str='',db:Session=Depends(get_db)):
    stmt=select(MenuItem).options(selectinload(MenuItem.restaurant))
    if q:stmt=stmt.where(MenuItem.name.ilike(f'%{q[:100]}%')|MenuItem.description.ilike(f'%{q[:100]}%'))
    if category:stmt=stmt.where(MenuItem.category.ilike(category[:80]))
    if restaurant_id:stmt=stmt.where(MenuItem.restaurant_id==restaurant_id)
    return {'items':[menu_json(m) for m in db.scalars(stmt.order_by(MenuItem.popular.desc(),MenuItem.name))]}

@router.get('/menu/{mid}', dependencies=[Depends(customer)])
def menu_detail(mid:str,db:Session=Depends(get_db)):
    m=db.get(MenuItem,mid)
    if not m:fail('Dish was not found.',404)
    return {'item':menu_json(m)}

@router.get('/cart')
def cart(db:Session=Depends(get_db),u:User=Depends(customer)):return cart_json(db,u)

@router.post('/cart/items',status_code=201)
def cart_add(data:CartAdd,db:Session=Depends(get_db),u:User=Depends(customer)):
    lock_customer(db,u);m=db.get(MenuItem,data.menu_item_id)
    if not m:fail('Dish was not found.',404)
    if not m.available:fail(f'{m.name} is sold out. Choose another dish.')
    if not m.restaurant.accepting_orders:fail(f'{m.restaurant.name} is not accepting new orders.')
    opts,_=options_price(m,data.options)
    # Identical customizations merge, while distinct notes/options remain separate.
    old=next((c for c in cart_rows(db,u.id) if c.menu_item_id==m.id and c.options==opts and c.note==data.note),None)
    if old:
        if old.quantity+data.quantity>99:fail('Quantity cannot exceed 99 for one cart item.')
        old.quantity+=data.quantity
    else:db.add(CartItem(user_id=u.id,menu_item_id=m.id,quantity=data.quantity,options=opts,note=data.note))
    db.flush();return cart_json(db,u)

@router.patch('/cart/items/{cid}')
def cart_edit(cid:str,data:CartEdit,db:Session=Depends(get_db),u:User=Depends(customer)):
    lock_customer(db,u);c=db.get(CartItem,cid)
    if not c or c.user_id!=u.id:fail('Cart item was not found.',404)
    if not c.menu_item.available or not c.menu_item.restaurant.accepting_orders:fail('This dish is unavailable. Remove it from the cart.')
    if data.quantity is not None:c.quantity=data.quantity
    if data.options is not None:c.options,_=options_price(c.menu_item,data.options)
    if data.note is not None:c.note=data.note
    db.flush();return cart_json(db,u)

@router.delete('/cart/items/{cid}')
def cart_remove(cid:str,db:Session=Depends(get_db),u:User=Depends(customer)):
    lock_customer(db,u);c=db.get(CartItem,cid)
    if not c or c.user_id!=u.id:fail('Cart item was not found.',404)
    db.delete(c);db.flush();return cart_json(db,u)

@router.delete('/cart')
def cart_clear(db:Session=Depends(get_db),u:User=Depends(customer)):
    lock_customer(db,u);db.execute(delete(CartItem).where(CartItem.user_id==u.id));db.flush();return cart_json(db,u)

@router.post('/cart/quote')
def cart_quote(data:Quote,db:Session=Depends(get_db),u:User=Depends(customer)):return quote(db,u,data)[0]

@router.post('/orders',status_code=201)
def place_order(data:Checkout,db:Session=Depends(get_db),u:User=Depends(customer)):
    o,p=checkout(db,u,data);result={'order':order_json(o)}
    if p:result['payment_url']=f'/payment/{p.id}'
    return result

@router.get('/orders')
def orders(db:Session=Depends(get_db),u:User=Depends(current)):
    stmt=order_query()
    if u.role=='customer':stmt=stmt.where(Order.customer_id==u.id)
    elif u.role=='restaurant':stmt=stmt.where(Order.id.in_(select(SubOrder.order_id).where(SubOrder.restaurant_id==owned_restaurant(db,u).id)),restaurant_visibility())
    elif u.role=='driver':stmt=stmt.where(Order.id.in_(select(Trip.order_id).where(Trip.driver_id==u.id)))
    return {'orders':[scoped_json(db,o,u) for o in db.scalars(stmt.order_by(Order.created_at.desc()))]}

@router.get('/orders/{oid}')
def order_detail(oid:str,db:Session=Depends(get_db),u:User=Depends(current)):
    o=get_order(db,oid);accessible(db,o,u);return {'order':scoped_json(db,o,u)}

@router.post('/orders/{oid}/cancel')
def cancel(oid:str,data:Reason,db:Session=Depends(get_db),u:User=Depends(customer)):
    o=get_order(db,oid,True);accessible(db,o,u);cancel_order(db,o,data.reason);db.flush();return {'order':order_json(o)}

@router.get('/payments/{pid}')
def payment_detail(pid:str,db:Session=Depends(get_db),u:User=Depends(current)):
    p=db.get(Payment,pid)
    if not p:fail('Payment was not found.',404)
    accessible(db,p.order,u)
    if u.role not in {'customer','admin'}:fail('Only the customer can view payment details.',403)
    return {'payment':payment_json(p)}

@router.post('/payments/{pid}/sandbox')
def sandbox_payment(pid:str,data:Sandbox,db:Session=Depends(get_db),u:User=Depends(customer)):
    if PAYMENT_PROVIDER!='sandbox':fail('Sandbox payments are disabled.',404)
    p=db.get(Payment,pid)
    if not p:fail('Payment was not found.',404)
    if p.order.customer_id!=u.id:fail('This payment belongs to another customer.',403)
    o=complete_payment(db,p,data.outcome,'sandbox-'+p.id)
    return {'order':order_json(o)}

@router.post('/payments/callback')
async def payment_callback(request:Request,db:Session=Depends(get_db)):
    body=await request.body();signature=request.headers.get('X-Payment-Signature','')
    expected=hmac.new(PAYMENT_SECRET.encode(),body,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,expected):
        log.warning('payment_callback_bad_signature');fail('Invalid payment callback signature.',403)
    try:data=Callback.model_validate_json(body)
    except Exception:fail('Payment callback payload is invalid.',422)
    p=db.get(Payment,data.payment_id)
    if not p:fail('Payment was not found.',404)
    return {'order':order_json(complete_payment(db,p,data.outcome,data.external_reference))}

@router.post('/orders/{oid}/retry-payment')
def retry_payment(oid:str,db:Session=Depends(get_db),u:User=Depends(customer)):
    o=get_order(db,oid,True);accessible(db,o,u)
    if o.payment_method!='online' or o.status not in {'awaiting_payment','payment_failed'}:fail('This order does not require a payment retry.',409)
    # Revalidate availability before another capture, while keeping agreed snapshots.
    for s in o.suborders:
        r=db.get(Restaurant,s.restaurant_id)
        if not r.accepting_orders:fail(f'{r.name} is not accepting orders. Cancel this order and try again later.')
        for i in s.items:
            if not db.get(MenuItem,i.menu_item_id).available:fail(f'{i.name} is sold out. Cancel this order and create a new cart.')
    p=next((p for p in o.payments if p.status=='pending'),None)
    if not p:p=create_payment(db,o);o.status='awaiting_payment';o.payment_status='pending'
    return {'payment_url':f'/payment/{p.id}','payment':payment_json(p)}

@router.post('/orders/{oid}/reviews',status_code=201)
def review(oid:str,data:ReviewInput,db:Session=Depends(get_db),u:User=Depends(customer)):
    o=get_order(db,oid,True);accessible(db,o,u)
    if o.status!='delivered':fail('Reviews are available after your order is delivered.',409)
    if data.target_type=='restaurant' and not any(s.restaurant_id==data.target_id and s.status=='delivered' for s in o.suborders):fail('Choose a restaurant that completed this order.')
    if data.target_type=='driver' and (not o.trip or o.trip.driver_id!=data.target_id):fail('Choose the driver who delivered this order.')
    if any(r.target_type==data.target_type and r.target_id==data.target_id for r in o.reviews):fail('You have already reviewed this part of the order.',409)
    r=Review(order_id=o.id,customer_id=u.id,**data.model_dump());db.add(r);o.reviews.append(r);db.flush();return {'order':order_json(o)}

@router.get('/restaurant/dashboard')
def restaurant_dashboard(db:Session=Depends(get_db),u:User=Depends(restaurant_user)):
    r=owned_restaurant(db,u);os=list(db.scalars(order_query().where(Order.id.in_(select(SubOrder.order_id).where(SubOrder.restaurant_id==r.id)),restaurant_visibility()).order_by(Order.created_at.desc())))
    today=now().astimezone(__import__('zoneinfo').ZoneInfo('Asia/Ho_Chi_Minh')).date();todays=[o for o in os if aware(o.created_at).astimezone(__import__('zoneinfo').ZoneInfo('Asia/Ho_Chi_Minh')).date()==today]
    subs=[s for o in os for s in o.suborders if s.restaurant_id==r.id]
    return {'restaurant':restaurant_json(db,r),'stats':{'orders_today':len(todays),'revenue_today':sum(s.subtotal-(s.discount if o.promo_code!='FREESHIP' else 0) for o in todays if o.status=='delivered' for s in o.suborders if s.restaurant_id==r.id and s.status=='delivered'),'pending_orders':sum(s.status=='pending' for s in subs),'total_orders':len(os)},'orders':[scoped_json(db,o,u) for o in os],'menu':[menu_json(m) for m in r.menu]}

@router.get('/restaurant/orders')
def restaurant_orders(db:Session=Depends(get_db),u:User=Depends(restaurant_user)):return orders(db,u)

@router.patch('/restaurant/profile')
def restaurant_profile(data:ProfileEdit,db:Session=Depends(get_db),u:User=Depends(restaurant_user)):
    r=owned_restaurant(db,u);r=db.scalar(select(Restaurant).where(Restaurant.id==r.id).with_for_update());r.accepting_orders=data.accepting_orders;return {'restaurant':restaurant_json(db,r)}

@router.post('/restaurant/menu',status_code=201)
def menu_create(data:MenuCreate,db:Session=Depends(get_db),u:User=Depends(restaurant_user)):
    r=owned_restaurant(db,u);db.scalar(select(Restaurant).where(Restaurant.id==r.id).with_for_update())
    if db.scalar(select(MenuItem).where(MenuItem.restaurant_id==r.id,MenuItem.code==data.code)):fail('This dish code is already used by your restaurant. Choose a unique code.',409)
    validate_menu_options(data.options);m=MenuItem(restaurant_id=r.id,**data.model_dump());db.add(m);db.flush();return {'item':menu_json(m)}

@router.patch('/restaurant/menu/{mid}')
def menu_update(mid:str,data:MenuEdit,db:Session=Depends(get_db),u:User=Depends(restaurant_user)):
    r=owned_restaurant(db,u);m=db.scalar(select(MenuItem).where(MenuItem.id==mid).with_for_update())
    if not m or m.restaurant_id!=r.id:fail('This dish was not found in your restaurant.',404)
    fields=data.model_dump(exclude_none=True)
    if 'code' in fields and db.scalar(select(MenuItem).where(MenuItem.restaurant_id==r.id,MenuItem.code==fields['code'],MenuItem.id!=mid)):fail('This dish code is already in use.',409)
    if 'options' in fields:validate_menu_options(fields['options'])
    for key,value in fields.items():setattr(m,key,value)
    db.flush();return {'item':menu_json(m)}

@router.delete('/restaurant/menu/{mid}')
def menu_delete(mid:str,db:Session=Depends(get_db),u:User=Depends(restaurant_user)):
    r=owned_restaurant(db,u);m=db.scalar(select(MenuItem).where(MenuItem.id==mid).with_for_update())
    if not m or m.restaurant_id!=r.id:fail('Dish was not found.',404)
    if not m.available:fail('Temporarily sold-out dishes must remain on the menu. Update their availability instead.',409)
    if db.scalar(select(OrderItem.id).where(OrderItem.menu_item_id==mid).limit(1)) or db.scalar(select(CartItem.id).where(CartItem.menu_item_id==mid).limit(1)):fail('This dish appears in an order or cart. Mark it sold out instead.',409)
    db.delete(m);return {'message':'Dish deleted.'}

@router.post('/restaurant/suborders/{sid}/status')
def restaurant_status(sid:str,data:RestaurantStatus,db:Session=Depends(get_db),u:User=Depends(restaurant_user)):
    s=db.get(SubOrder,sid)
    if not s or s.restaurant_id!=owned_restaurant(db,u).id:fail('Restaurant order was not found.',404)
    o=get_order(db,s.order_id,True);s=next(x for x in o.suborders if x.id==sid)
    if o.status in DONE or o.status in {'awaiting_payment','incident'}:fail('This order cannot be updated in its current state.',409)
    if s.status==data.status:return {'order':scoped_json(db,o,u)}
    allowed={'pending':{'accepted','rejected'},'accepted':{'preparing','rejected'},'preparing':{'ready'}}
    if data.status not in allowed.get(s.status,set()):fail(f'Cannot change {s.status} to {data.status}. Follow the preparation steps in order.',409)
    if data.status=='rejected':credit_suborder(db,o,s,data.reason)
    else:
        if data.status=='accepted' and not db.get(Restaurant,s.restaurant_id).accepting_orders:fail('Enable accepting orders in your restaurant settings first.')
        s.status=data.status;event(db,o,data.status,f'{s.restaurant_name} '+{'accepted':'accepted your order.','preparing':'is preparing your food.','ready':'has your food ready for pickup.'}[data.status]);refresh_status(db,o)
    db.flush();dispatch(db,o);return {'order':scoped_json(db,o,u)}

@router.get('/driver/dashboard')
def driver_dashboard(db:Session=Depends(get_db),u:User=Depends(driver_user)):
    d=db.get(Driver,u.id)
    if not d:fail('Driver profile is missing. Contact an administrator.',404)
    os=list(db.scalars(order_query().where(Order.id.in_(select(Trip.order_id).where(Trip.driver_id==u.id))).order_by(Order.created_at.desc())))
    active=[o for o in os if o.trip.status not in {'delivered','cancelled','declined'}];history=[o for o in os if o.trip.status in {'delivered','cancelled'}]
    finished=[o.trip for o in os if o.trip.status=='delivered']
    return {'driver':driver_json(d),'stats':{'completed_trips':len(finished),'earnings':sum(t.delivery_fee for t in finished),'total_cod':sum(t.cod_collected for t in finished)},'trips':[order_json(o) for o in active],'history':[order_json(o) for o in history]}

@router.post('/driver/status')
def driver_status(data:Online,db:Session=Depends(get_db),u:User=Depends(driver_user)):
    d=db.scalar(select(Driver).where(Driver.id==u.id).with_for_update())
    if not d:fail('Driver profile is missing.',404)
    if not data.online and not d.available:fail('Finish or decline your active trip before going offline.',409)
    d.online=data.online;d.last_location_at=now();db.flush()
    # Commit driver state before claiming order locks; avoids inverse lock ordering.
    db.commit()
    if data.online:retry_waiting_dispatch(db)
    return {'driver':driver_json(d)}

@router.post('/driver/location')
def driver_location(data:Location,db:Session=Depends(get_db),u:User=Depends(driver_user)):
    d=db.scalar(select(Driver).where(Driver.id==u.id).with_for_update())
    if not d:fail('Driver profile is missing.',404)
    d.lat=data.lat;d.lng=data.lng;d.last_location_at=now();db.flush();return {'driver':driver_json(d)}

def trip_order(db,tid,u):
    t=db.scalar(select(Trip).where(Trip.id==tid))
    if not t or t.driver_id!=u.id:fail('This trip is not assigned to you.',404)
    o=get_order(db,t.order_id,True)
    # Refresh trip after waiting for order lock (offer may have been reassigned).
    db.refresh(t)
    if t.driver_id!=u.id:fail('This trip offer has been reassigned.',409)
    return t,o

@router.post('/driver/trips/{tid}/accept')
def trip_accept(tid:str,db:Session=Depends(get_db),u:User=Depends(driver_user)):
    t,o=trip_order(db,tid,u)
    if t.status!='offered':fail('This trip is no longer awaiting acceptance.',409)
    if not t.pickups or not o.address or not o.phone:fail('Trip details are incomplete. Contact support.',409)
    t.status='accepted';o.status='picking_up';event(db,o,'picking_up',f'{u.name} accepted your trip and is heading to the first restaurant.');return {'order':order_json(o)}

@router.post('/driver/trips/{tid}/decline')
def trip_decline(tid:str,data:Reason,db:Session=Depends(get_db),u:User=Depends(driver_user)):
    t,o=trip_order(db,tid,u)
    if t.status!='offered':fail('Only a new trip offer can be declined.',409)
    t.status='declined';t.declined_driver_ids=list(set(t.declined_driver_ids+[u.id]));t.driver.available=True
    event(db,o,'driver_declined',f'The driver declined the offer. Finding another driver. {data.reason}');db.flush();dispatch(db,o);return {'order':order_json(o)}

@router.post('/driver/trips/{tid}/pickup')
def trip_pickup(tid:str,data:Pickup,db:Session=Depends(get_db),u:User=Depends(driver_user)):
    t,o=trip_order(db,tid,u)
    if t.status not in {'accepted','picking_up'}:fail('Accept the trip before collecting food.',409)
    next_stop=next((p for p in t.pickups if not p['picked_up']),None)
    if not next_stop or next_stop['suborder_id']!=data.suborder_id:fail('Collect food in the displayed stop order.',409)
    s=next(s for s in o.suborders if s.id==data.suborder_id)
    if s.status!='ready':fail(f'{s.restaurant_name} has not marked this order ready. Wait for confirmation.',409)
    t.pickups=[dict(p,picked_up=True) if p['suborder_id']==s.id else p for p in t.pickups];s.status='picked_up';t.status='picking_up';event(db,o,'picked_up',f'Food collected from {s.restaurant_name}.')
    if all(p['picked_up'] for p in t.pickups):
        t.status='delivering';o.status='delivering'
        for sub in o.suborders:
            if sub.status=='picked_up':sub.status='delivering'
        event(db,o,'delivering','All pickups complete. Your driver is on the way to you.')
    return {'order':order_json(o)}

@router.post('/driver/trips/{tid}/complete')
def trip_complete(tid:str,data:Complete,db:Session=Depends(get_db),u:User=Depends(driver_user)):
    t,o=trip_order(db,tid,u)
    if t.status=='delivered':return {'order':order_json(o)}
    if t.status!='delivering' or not t.pickups or not all(p['picked_up'] for p in t.pickups):fail('Collect food from every restaurant before completing delivery.',409)
    if o.payment_method=='cod' and not data.cod_received:fail(f'Confirm collection of {t.cod_amount:,} VND before completing the delivery.')
    # A completion timestamp belongs to a reconciliation period only after it
    # owns the same lock used to close that period.
    db.scalar(select(DispatchConfig).where(DispatchConfig.id==1).with_for_update())
    t.status='delivered';t.completed_at=now();t.driver.available=True;t.cod_collected=t.cod_amount if o.payment_method=='cod' else 0;o.status='delivered';o.delivered_at=t.completed_at
    if o.payment_method=='cod':o.payment_status='collected'
    for s in o.suborders:
        if s.status not in {'rejected','cancelled'}:s.status='delivered'
    event(db,o,'delivered','Your order was delivered. Enjoy your meal!');db.flush();return {'order':order_json(o)}

@router.post('/driver/trips/{tid}/incident')
def trip_incident(tid:str,data:Reason,db:Session=Depends(get_db),u:User=Depends(driver_user)):
    t,o=trip_order(db,tid,u)
    if t.status not in {'accepted','picking_up','delivering'}:fail('Incidents can be reported only for an active trip.',409)
    if len(data.reason)<5:fail('Describe the problem in at least 5 characters so support can help.')
    t.status='incident';o.status='incident';event(db,o,'incident',f'Driver reported an incident: {data.reason}. Support has been notified.');return {'order':order_json(o)}

@router.get('/reports')
def reports(from_date:date|None=None,to_date:date|None=None,db:Session=Depends(get_db),u:User=Depends(reporter)):
    if from_date and to_date and from_date>to_date:fail('From date must be before or equal to to date.')
    stmt=order_query()
    zone=__import__('zoneinfo').ZoneInfo('Asia/Ho_Chi_Minh')
    if from_date:stmt=stmt.where(Order.created_at>=datetime.combine(from_date,datetime.min.time(),zone).astimezone(timezone.utc))
    if to_date:stmt=stmt.where(Order.created_at<datetime.combine(to_date+timedelta(days=1),datetime.min.time(),zone).astimezone(timezone.utc))
    rid=owned_restaurant(db,u).id if u.role=='restaurant' else None
    if rid:stmt=stmt.where(Order.id.in_(select(SubOrder.order_id).where(SubOrder.restaurant_id==rid)),restaurant_visibility())
    os=list(db.scalars(stmt.order_by(Order.created_at.desc())));completed=[o for o in os if o.status=='delivered'];cfg=config(db)
    subs=[s for o in completed for s in o.suborders if s.status=='delivered' and (not rid or s.restaurant_id==rid)]
    food_discounts=sum(s.discount for s in subs if s.order.promo_code!='FREESHIP')
    gross=sum(s.total for s in subs);food=sum(s.subtotal for s in subs);fees=sum(s.delivery_fee for s in subs);discounts=sum(s.discount for s in subs);commission=sum(round(max(0,s.subtotal-(s.discount if s.order.promo_code!='FREESHIP' else 0))*cfg.commission_rate) for s in subs)
    refunds=sum(sum(s.total for s in o.suborders if s.status in {'rejected','cancelled'} and (not rid or s.restaurant_id==rid)) for o in os)
    daily=defaultdict(lambda:{'orders':0,'revenue':0})
    for o in os:
        key=aware(o.created_at).astimezone(zone).date().isoformat();daily[key]['orders']+=1
        if o.status=='delivered':daily[key]['revenue']+=sum(s.total for s in o.suborders if s.status=='delivered' and (not rid or s.restaurant_id==rid))
    return {'summary':{'total_orders':len(os),'completed_orders':len(completed),'gross_revenue':gross,'food_revenue':food,'delivery_fees':fees,'discounts':discounts,'food_discounts':food_discounts,'delivery_discounts':discounts-food_discounts,'refunds':refunds,'commission':commission,'net_revenue':food-food_discounts-commission},'daily':[{'date':k,**v} for k,v in sorted(daily.items())],'orders':[scoped_json(db,o,u) for o in os]}

@router.get('/admin/dashboard')
def admin_dashboard(db:Session=Depends(get_db),u:User=Depends(admin)):
    os=list(db.scalars(order_query().order_by(Order.created_at.desc())));users=list(db.scalars(select(User).order_by(User.created_at.desc())));ss=list(db.scalars(select(Settlement).order_by(Settlement.period_start.desc())))
    c=config(db)
    return {'stats':{'total_orders':db.scalar(select(func.count(Order.id))),'active_orders':sum(o.status not in DONE for o in os),'revenue':sum(o.total-o.refund_amount for o in os if o.status=='delivered'),'total_customers':sum(v.role=='customer' for v in users),'online_drivers':db.scalar(select(func.count(Driver.id)).where(Driver.online.is_(True))),'pending_settlements':sum(s.status=='pending' for s in ss)},'orders':[order_json(o) for o in os],'users':[view_user(db,v) for v in users],'drivers':[driver_json(d) for d in db.scalars(select(Driver))],'config':{k:getattr(c,k) for k in ['max_group_distance_km','dispatch_radius_km','base_delivery_fee','per_km_fee','commission_rate']},'settlements':[settlement_json(s) for s in ss]}

@router.patch('/admin/users/{id_}')
def user_update(id_:str,data:AccountEdit,db:Session=Depends(get_db),u:User=Depends(admin)):
    v=db.scalar(select(User).where(User.id==id_).with_for_update())
    if not v:fail('Account was not found.',404)
    if v.id==u.id and not data.active:fail('You cannot deactivate your own administrator account.')
    if not data.active and v.role=='driver':
        d=db.get(Driver,v.id)
        if d and not d.available:fail('Resolve this driver’s active trip before deactivating the account.',409)
        if d:d.online=False
    if not data.active and v.role=='restaurant':
        partner=db.scalar(select(Restaurant).where(Restaurant.owner_id==v.id).with_for_update())
        if partner:partner.accepting_orders=False
    v.active=data.active;log.info('account_state_changed actor=%s target=%s active=%s',u.id,v.id,v.active);return {'user':view_user(db,v)}

@router.patch('/admin/config')
def config_update(data:ConfigEdit,db:Session=Depends(get_db),u:User=Depends(admin)):
    c=config(db);db.scalar(select(DispatchConfig).where(DispatchConfig.id==1).with_for_update())
    for key,value in data.model_dump(exclude_none=True).items():setattr(c,key,value)
    return {'config':{k:getattr(c,k) for k in ['max_group_distance_km','dispatch_radius_km','base_delivery_fee','per_km_fee','commission_rate']}}

@router.post('/admin/orders/{oid}/dispatch')
def admin_dispatch(oid:str,db:Session=Depends(get_db),u:User=Depends(admin)):
    o=get_order(db,oid,True)
    if not dispatch(db,o):db.flush()
    return {'order':order_json(o)}

@router.post('/admin/orders/{oid}/resolve')
def admin_resolve(oid:str,data:Resolve,db:Session=Depends(get_db),u:User=Depends(admin)):
    o=get_order(db,oid,True)
    if data.action=='cancel':cancel_order(db,o,data.reason,True)
    else:
        if o.status=='incident' and o.trip:
            if any(p['picked_up'] for p in o.trip.pickups):fail('Food was already collected. Cancel/refund the incident or contact the assigned driver; reassignment would duplicate pickups.',409)
            o.trip.driver.available=True;o.trip.status='declined';o.trip.declined_driver_ids=list(set(o.trip.declined_driver_ids+[o.trip.driver_id]));refresh_status(db,o)
        if o.trip and o.trip.status=='declined':o.trip.declined_driver_ids=[]
        dispatch(db,o,True)
    event(db,o,o.status,f'Administrator resolution: {data.reason or data.action}');db.flush();return {'order':order_json(o)}

@router.get('/admin/settlements')
def settlements(db:Session=Depends(get_db),u:User=Depends(admin)):
    return {'settlements':[settlement_json(s) for s in db.scalars(select(Settlement).order_by(Settlement.period_start.desc(),Settlement.party_type))]}

@router.post('/admin/settlements/run')
def settlements_run(data:Reconcile,db:Session=Depends(get_db),u:User=Depends(admin)):
    rows=reconcile(db,data.include_current);return {'created':len(rows),'settlements':[settlement_json(s) for s in db.scalars(select(Settlement).order_by(Settlement.period_start.desc()))]}

@router.post('/admin/settlements/{sid}/paid')
def settlement_paid(sid:str,db:Session=Depends(get_db),u:User=Depends(admin)):
    # Reconcile and serialize on the same config lock before closing a period.
    reconcile(db)
    s=db.scalar(select(Settlement).where(Settlement.id==sid).with_for_update().execution_options(populate_existing=True))
    if not s:fail('Settlement was not found.',404)
    if aware(s.period_end)>now():fail('This weekly period is still open. Mark it paid after Sunday 23:59 Vietnam time.',409)
    if s.status!='paid':s.status='paid';s.paid_at=now()
    return {'settlement':settlement_json(s)}

@router.post('/admin/users',status_code=201)
def account_create(data:AccountCreate,db:Session=Depends(get_db),u:User=Depends(admin)):
    if db.scalar(select(User).where(User.email==data.email.lower())):fail('This email is already registered.',409)
    if data.role=='restaurant' and not data.restaurant:fail('Restaurant accounts require restaurant name, category, address and coordinates.')
    if data.role!='restaurant' and data.restaurant:fail('Restaurant details apply only to restaurant accounts.')
    v=User(name=data.name,email=data.email.lower(),phone=data.phone,password_hash=hash_password(data.password),role=data.role,active=True);db.add(v);db.flush()
    if v.role=='driver':db.add(Driver(id=v.id,online=False,available=True,lat=10.7769,lng=106.7009,last_location_at=now()))
    if v.role=='restaurant':db.add(Restaurant(owner_id=v.id,**data.restaurant.model_dump(),accepting_orders=False,delivery_minutes=30,featured=False,tags=[]))
    db.flush();log.info('account_created actor=%s target=%s role=%s',u.id,v.id,v.role);return {'user':view_user(db,v)}
