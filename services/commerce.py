"""Server-authoritative cart, billing, dispatch and order state transitions."""
from datetime import datetime, timezone, timedelta
from itertools import permutations
from math import radians, sin, cos, asin, sqrt, ceil
from collections import defaultdict
from fastapi import HTTPException
from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload
from models.entities import User, Restaurant, MenuItem, CartItem, Order, SubOrder, OrderItem, OrderEvent, Payment, Driver, Trip, Review, DispatchConfig, Refund, now, uid
from properties.config import PAYMENT_PROVIDER

LIVE = {'pending','accepted','preparing','ready','picking_up','picked_up','delivering'}
DONE = {'delivered','cancelled','rejected','payment_failed'}

def fail(detail, status=400): raise HTTPException(status, detail)
def iso(value):
    if value is None: return None
    if value.tzinfo is None: value=value.replace(tzinfo=timezone.utc)
    return value.isoformat()
def distance(a,b):
    la1,lo1,la2,lo2=map(radians,[a[0],a[1],b[0],b[1]])
    return 6371*2*asin(min(1,sqrt(sin((la2-la1)/2)**2+cos(la1)*cos(la2)*sin((lo2-lo1)/2)**2)))
def config(db):
    c=db.get(DispatchConfig,1)
    if not c: c=DispatchConfig(id=1);db.add(c);db.flush()
    return c

def user_json(u, restaurant_id=None):
    return {'id':u.id,'name':u.name,'email':u.email,'phone':u.phone,'role':u.role,'active':u.active,'restaurant_id':restaurant_id}
def restaurant_json(db,r):
    rating,count=db.execute(select(func.avg(Review.rating),func.count(Review.id)).where(Review.target_type=='restaurant',Review.target_id==r.id)).one()
    return {k:getattr(r,k) for k in ['id','name','description','category','image','address','lat','lng','accepting_orders','delivery_minutes','featured','tags']} | {'rating':round(rating,1) if rating else None,'review_count':count,'delivery_fee':config(db).base_delivery_fee}
def menu_json(m):
    return {k:getattr(m,k) for k in ['id','restaurant_id','code','name','description','category','price','image','available','popular','options']} | {'restaurant_name':m.restaurant.name}
def driver_json(d):
    return {'id':d.id,'name':d.user.name,'phone':d.user.phone,'online':d.online,'available':d.available,'lat':d.lat,'lng':d.lng,'last_location_at':iso(d.last_location_at)}
def payment_json(p): return {'id':p.id,'order_id':p.order_id,'amount':p.amount,'status':p.status,'provider':p.provider,'checkout_url':f'/payment/{p.id}'}
def event(db,o,status,message):
    e=OrderEvent(order_id=o.id,status=status,message=message);db.add(e)
    if 'events' in o.__dict__: o.events.append(e)

def order_query():
    return select(Order).options(selectinload(Order.suborders).selectinload(SubOrder.items), selectinload(Order.events),selectinload(Order.reviews),selectinload(Order.refunds),selectinload(Order.payments),selectinload(Order.customer),selectinload(Order.trip).selectinload(Trip.driver).selectinload(Driver.user))
def get_order(db,oid,lock=False):
    stmt=order_query().where(Order.id==oid)
    if lock: stmt=stmt.with_for_update().execution_options(populate_existing=True)
    o=db.scalar(stmt)
    if not o: fail('Order was not found.',404)
    return o

def order_json(o):
    trip=None
    if o.trip and o.trip.status not in {'declined','cancelled'}:
        t=o.trip
        trip={'id':t.id,'code':t.code,'status':t.status,'driver':driver_json(t.driver),'pickups':t.pickups,'delivery_fee':t.delivery_fee,'cod_amount':t.cod_amount,'cod_collected':t.cod_collected}
    return {k:getattr(o,k) for k in ['id','code','status','payment_method','payment_status','subtotal','delivery_fee','discount','total','refund_amount','address','lat','lng','phone','note','promo_code']} | {
        'created_at':iso(o.created_at),'delivered_at':iso(o.delivered_at),'payable_total':o.total-o.refund_amount,
        'customer':{'name':o.customer.name,'phone':o.phone},'trip':trip,
        'suborders':[{k:getattr(s,k) for k in ['id','restaurant_id','restaurant_name','address','lat','lng','status','subtotal','delivery_fee','discount','total']} | {'items':[{k:getattr(i,k) for k in ['id','name','quantity','options','note','unit_price','line_total']} for i in s.items]} for s in o.suborders],
        'events':[{'id':e.id,'status':e.status,'message':e.message,'created_at':iso(e.created_at)} for e in o.events],
        'reviews':[{k:getattr(r,k) for k in ['id','target_type','target_id','rating','comment']} for r in o.reviews],
        'refunds':[{'id':r.id,'suborder_id':r.suborder_id,'amount':r.amount,'status':r.status,'reason':r.reason,'provider_reference':r.provider_reference,'created_at':iso(r.created_at)} for r in o.refunds],
        'can_review':o.status=='delivered','payment_id':next((p.id for p in reversed(o.payments) if p.status=='pending'),None)}

def validate_menu_options(options):
    if set(options)-{'sizes','sugar','ice','toppings'}: fail('Options can contain only sizes, sugar, ice and toppings.')
    for key in ('sizes','toppings'):
        values=options.get(key,[])
        if not isinstance(values,list) or len(values)>20: fail(f'{key} must be a list with at most 20 entries.')
        names=[]
        for v in values:
            if not isinstance(v,dict) or set(v)-{'name','price'} or not isinstance(v.get('name'),str) or not v['name'].strip() or len(v['name'])>80 or type(v.get('price')) is not int or not 0<=v['price']<=1000000:
                fail(f'Each {key} option needs a name and non-negative integer price.')
            names.append(v['name'])
        if len(set(names))!=len(names): fail(f'{key} option names must be unique.')
    for key in ('sugar','ice'):
        values=options.get(key,[])
        if not isinstance(values,list) or len(values)>20 or any(not isinstance(v,str) or not v.strip() or len(v)>80 for v in values) or len(set(values))!=len(values): fail(f'{key} must be a list of unique, non-empty text values.')
    return options

def options_price(m,chosen):
    if not isinstance(chosen,dict) or set(chosen)-{'size','sugar','ice','toppings'}: fail('Choose valid size, sugar, ice and topping options.')
    schema=m.options or {}; normalized={};extra=0
    sizes=schema.get('sizes',[])
    for key,plural in [('size','sizes'),('sugar','sugar'),('ice','ice')]:
        allowed=schema.get(plural,[])
        if not allowed:
            if chosen.get(key) not in (None,''): fail(f'{m.name}: {key} is not offered for this dish.')
            continue
        names=[x['name'] for x in allowed] if key=='size' else allowed
        value=chosen.get(key) or names[0]
        if value not in names: fail(f'{m.name}: select a valid {key}.')
        normalized[key]=value
        if key=='size': extra+=next(x['price'] for x in sizes if x['name']==value)
    toppings=chosen.get('toppings',[])
    if not isinstance(toppings,list) or any(not isinstance(t,str) for t in toppings) or len(toppings)!=len(set(toppings)): fail('Toppings must be a list of distinct choices.')
    offered={t['name']:t['price'] for t in schema.get('toppings',[])}
    for topping in toppings:
        if topping not in offered: fail(f'{m.name}: topping {topping} is unavailable.')
        extra+=offered[topping]
    normalized['toppings']=toppings
    return normalized,extra

def lock_customer(db,u):
    db.scalar(select(User).where(User.id==u.id).with_for_update())
def cart_rows(db,uid_): return list(db.scalars(select(CartItem).where(CartItem.user_id==uid_).options(selectinload(CartItem.menu_item).selectinload(MenuItem.restaurant)).order_by(CartItem.id)))
def cart_json(db,u):
    items=[];groups={}
    for c in cart_rows(db,u.id):
        m=c.menu_item
        try: opts,extra=options_price(m,c.options)
        except HTTPException: opts,extra=c.options,0
        item={'id':c.id,'menu_item_id':m.id,'restaurant_id':m.restaurant_id,'restaurant_name':m.restaurant.name,'name':m.name,'image':m.image,'quantity':c.quantity,'options':opts,'note':c.note,'base_price':m.price,'extra_price':extra,'unit_price':m.price+extra,'line_total':(m.price+extra)*c.quantity,'available':m.available and m.restaurant.accepting_orders}
        items.append(item)
        g=groups.setdefault(m.restaurant_id,{'restaurant_id':m.restaurant_id,'restaurant_name':m.restaurant.name,'items':[],'subtotal':0});g['items'].append(item);g['subtotal']+=item['line_total']
    return {'items':items,'groups':list(groups.values()),'subtotal':sum(i['line_total'] for i in items),'item_count':sum(i['quantity'] for i in items)}

def quote(db,u,data,lock=False):
    rows=cart_rows(db,u.id)
    if not rows: fail('Your cart is empty. Add a dish before checkout.')
    menus={c.menu_item_id:c.menu_item for c in rows}
    if lock:
        for m in db.scalars(select(MenuItem).where(MenuItem.id.in_(menus)).order_by(MenuItem.id).with_for_update().execution_options(populate_existing=True)): menus[m.id]=m
    restaurants={m.restaurant_id:m.restaurant for m in menus.values()}
    if lock:
        restaurants={r.id:r for r in db.scalars(select(Restaurant).where(Restaurant.id.in_(restaurants)).order_by(Restaurant.id).with_for_update().execution_options(populate_existing=True))}
    cfg=config(db);rs=list(restaurants.values());groups={}
    for i,r in enumerate(rs):
        if not r.accepting_orders: fail(f'{r.name} is not accepting orders. Remove its dishes or try again later.')
        for other in rs[i+1:]:
            if distance((r.lat,r.lng),(other.lat,other.lng))>cfg.max_group_distance_km: fail(f'{r.name} and {other.name} are more than {cfg.max_group_distance_km:g} km apart. Place separate orders.')
        km=distance((r.lat,r.lng),(data.lat,data.lng))
        if km>30: fail(f'The delivery address is outside the 30 km service area for {r.name}.')
        fee=cfg.base_delivery_fee+ceil(km)*cfg.per_km_fee
        groups[r.id]={'restaurant_id':r.id,'restaurant_name':r.name,'subtotal':0,'delivery_fee':fee,'discount':0,'distance_km':round(km,2),'items':[]}
    for c in rows:
        m=menus[c.menu_item_id]
        if not m.available: fail(f'{m.name} is sold out. Remove it from your cart to continue.')
        opts,extra=options_price(m,c.options);price=m.price+extra
        groups[m.restaurant_id]['items'].append({'menu_item_id':m.id,'name':m.name,'quantity':c.quantity,'options':opts,'note':c.note,'unit_price':price,'line_total':price*c.quantity})
        groups[m.restaurant_id]['subtotal']+=price*c.quantity
    subtotal=sum(g['subtotal'] for g in groups.values());fees=sum(g['delivery_fee'] for g in groups.values());code=data.promo_code.upper()
    if code not in ('','WELCOME10','FREESHIP'): fail('Promo code is invalid. Use WELCOME10 or FREESHIP, or remove the code.')
    discount=min(subtotal//10,50000) if code=='WELCOME10' else min(fees,30000) if code=='FREESHIP' else 0
    # Largest remainder allocation preserves the invoice total exactly.
    weight_key='delivery_fee' if code=='FREESHIP' else 'subtotal';denominator=sum(g[weight_key] for g in groups.values()) or 1
    remaining=discount
    values=list(groups.values())
    for g in values: g['discount']=discount*g[weight_key]//denominator;remaining-=g['discount']
    for g in sorted(values,key=lambda g:discount*g[weight_key]%denominator,reverse=True)[:remaining]: g['discount']+=1
    for g in values: g['total']=g['subtotal']+g['delivery_fee']-g['discount']
    public={'subtotal':subtotal,'delivery_fee':fees,'discount':discount,'total':subtotal+fees-discount,'groups':[{k:v for k,v in g.items() if k!='items'} for g in values],'promo_code':code}
    return public,values,restaurants

def create_payment(db,o):
    if PAYMENT_PROVIDER!='sandbox': fail('Online payments are unavailable until a production payment provider is integrated. Please choose COD.',503)
    p=Payment(order_id=o.id,provider='sandbox',amount=o.total,status='pending');db.add(p);db.flush()
    if 'payments' in o.__dict__: o.payments.append(p)
    return p

def checkout(db,u,data):
    lock_customer(db,u)
    old=db.scalar(order_query().where(Order.customer_id==u.id,Order.idempotency_key==data.idempotency_key))
    if old: return old,next((p for p in reversed(old.payments) if p.status=='pending'),None)
    q,groups,restaurants=quote(db,u,data,True)
    if data.payment_method=='online' and PAYMENT_PROVIDER!='sandbox': fail('Online payments are unavailable. Please choose COD.',503)
    o=Order(id=uid(),code='GT-'+uid().replace('-','')[:10].upper(),customer_id=u.id,idempotency_key=data.idempotency_key,status='awaiting_payment' if data.payment_method=='online' else 'pending',payment_method=data.payment_method,payment_status='pending' if data.payment_method=='online' else 'cod_pending',subtotal=q['subtotal'],delivery_fee=q['delivery_fee'],discount=q['discount'],total=q['total'],refund_amount=0,address=data.address,lat=data.lat,lng=data.lng,phone=data.phone,note=data.note,promo_code=q['promo_code'])
    db.add(o);db.flush()
    for g in groups:
        r=restaurants[g['restaurant_id']]
        s=SubOrder(order_id=o.id,restaurant_id=r.id,restaurant_name=r.name,address=r.address,lat=r.lat,lng=r.lng,status='awaiting_payment' if data.payment_method=='online' else 'pending',subtotal=g['subtotal'],delivery_fee=g['delivery_fee'],discount=g['discount'],total=g['total']);db.add(s);db.flush()
        for item in g['items']: db.add(OrderItem(suborder_id=s.id,**item))
    p=create_payment(db,o) if data.payment_method=='online' else None
    event(db,o,o.status,'Order created. Complete sandbox payment to notify restaurants.' if p else 'Order placed. Waiting for restaurants to confirm.')
    db.execute(delete(CartItem).where(CartItem.user_id==u.id));db.flush();db.expire(o)
    return get_order(db,o.id),p

def complete_payment(db,p,outcome,reference):
    # Lock order first everywhere to keep callback and cancellation serialization consistent.
    o=get_order(db,p.order_id,True)
    p=db.scalar(select(Payment).where(Payment.id==p.id).with_for_update().execution_options(populate_existing=True))
    if p.status!='pending':
        if p.status!=('paid' if outcome=='success' else 'failed'): fail('This transaction already has a different final result.',409)
        return o
    if o.status not in {'awaiting_payment','payment_failed'}: fail('This order can no longer accept payment.',409)
    if p.amount!=o.total: fail('Payment amount does not match the invoice.',409)
    other=db.scalar(select(Payment).where(Payment.external_reference==reference,Payment.id!=p.id))
    if other: fail('This payment reference has already been used.',409)
    p.external_reference=reference
    if outcome=='success':
        p.status='paid';o.payment_status='paid';o.status='pending'
        for s in o.suborders:s.status='pending'
        event(db,o,'paid','Payment confirmed. Restaurants have been notified.')
    else:
        p.status='failed';o.payment_status='failed';o.status='payment_failed'
        event(db,o,'payment_failed','Payment failed. No money was captured. Retry securely from your order.')
    db.flush();return o

def refresh_status(db,o):
    active=[s for s in o.suborders if s.status not in {'rejected','cancelled'}]
    if not active: o.status='cancelled';return
    if o.trip and o.trip.status in {'accepted','picking_up','delivering','delivered','incident'}:
        o.status={'accepted':'picking_up','picking_up':'picking_up','delivering':'delivering','delivered':'delivered','incident':'incident'}[o.trip.status];return
    if any(s.status=='pending' for s in active):o.status='pending'
    elif any(s.status=='preparing' for s in active):o.status='preparing'
    elif all(s.status=='ready' for s in active):o.status='ready'
    else:o.status='accepted'

def route_stops(start,subs,destination):
    def coord(s):return(s.lat,s.lng)
    if len(subs)<=7:
        candidates=permutations(subs)
        return list(min(candidates,key=lambda seq:distance(start,coord(seq[0]))+sum(distance(coord(a),coord(b)) for a,b in zip(seq,seq[1:]))+distance(coord(seq[-1]),destination)))
    remaining=list(subs);ordered=[];pos=start
    while remaining:
        nearest=min(remaining,key=lambda s:distance(pos,coord(s)));remaining.remove(nearest);ordered.append(nearest);pos=coord(nearest)
    return ordered

def dispatch(db,o,force=False):
    active=[s for s in o.suborders if s.status not in {'rejected','cancelled'}]
    if not active or o.status in DONE or o.status in {'awaiting_payment','incident'} or any(s.status in {'pending','awaiting_payment'} for s in active):return False
    t=o.trip
    if t and t.status not in {'declined','cancelled'}:return True
    cfg=config(db);excluded=t.declined_driver_ids if t else []
    cutoff=now()-timedelta(minutes=2)
    drivers=list(db.scalars(select(Driver).join(User).where(Driver.online.is_(True),Driver.available.is_(True),User.active.is_(True),Driver.last_location_at>=cutoff).with_for_update(skip_locked=True,of=Driver)))
    drivers=[d for d in drivers if d.id not in excluded and min(distance((d.lat,d.lng),(s.lat,s.lng)) for s in active)<=cfg.dispatch_radius_km]
    if not drivers:
        if not o.events or o.events[-1].status!='awaiting_driver':event(db,o,'awaiting_driver','No nearby available driver yet. Dispatch will retry when a driver comes online.')
        return False
    d=min(drivers,key=lambda d:min(distance((d.lat,d.lng),(s.lat,s.lng)) for s in active));d.available=False
    stops=route_stops((d.lat,d.lng),active,(o.lat,o.lng));pickups=[{'suborder_id':s.id,'restaurant_name':s.restaurant_name,'address':s.address,'lat':s.lat,'lng':s.lng,'picked_up':False,'sequence':i+1} for i,s in enumerate(stops)]
    if not t:
        t=Trip(id=uid(),code='TR-'+uid().replace('-','')[:10].upper(),order_id=o.id,driver_id=d.id,status='offered',pickups=pickups,declined_driver_ids=[],delivery_fee=sum(s.delivery_fee for s in active),cod_amount=sum(s.total for s in active) if o.payment_method=='cod' else 0);db.add(t);o.trip=t
    else:
        t.driver_id=d.id;t.driver=d;t.status='offered';t.created_at=now();t.pickups=pickups;t.delivery_fee=sum(s.delivery_fee for s in active);t.cod_amount=sum(s.total for s in active) if o.payment_method=='cod' else 0
    event(db,o,'driver_offered',f'A delivery offer was sent to {d.user.name}.');db.flush();return True

def retry_waiting_dispatch(db):
    for o in db.scalars(order_query().where(Order.status.in_(['accepted','preparing','ready'])).with_for_update(skip_locked=True).execution_options(populate_existing=True)):
        t=o.trip
        if t and t.status=='offered':
            offered=t.created_at if t.created_at.tzinfo else t.created_at.replace(tzinfo=timezone.utc)
            if now()-offered>=timedelta(seconds=60):
                t.status='declined';t.declined_driver_ids=list(set(t.declined_driver_ids+[t.driver_id]));t.driver.available=True
                event(db,o,'driver_offer_expired','The driver did not answer within 60 seconds. Finding another nearby driver.')
                db.flush()
        if not o.trip or o.trip.status=='declined':dispatch(db,o)

def record_refund(db,o,amount,reason,suborder_id=None):
    if amount<=0 or o.payment_method!='online' or o.payment_status not in {'paid','partially_refunded'}:return
    p=next((p for p in o.payments if p.status=='paid'),None)
    if not p:fail('Captured payment record is missing. Contact support before refunding.',409)
    if p.provider!='sandbox':fail('The configured payment provider must confirm this refund before the order can be credited.',503)
    refund=Refund(order_id=o.id,payment_id=p.id,suborder_id=suborder_id,amount=amount,status='refunded',reason=reason[:500],provider_reference='sandbox-refund-'+uid());db.add(refund)
    if 'refunds' in o.__dict__:o.refunds.append(refund)

def credit_suborder(db,o,s,reason):
    if s.status in {'rejected','cancelled'}:return
    if o.trip and o.trip.status in {'accepted','picking_up','delivering','delivered'}:fail('Contact an administrator to change an order after its driver has accepted.',409)
    record_refund(db,o,s.total,reason or 'Restaurant declined the order',s.id)
    s.status='rejected';o.refund_amount+=s.total
    if o.payment_method=='online' and o.payment_status in {'paid','partially_refunded'}:
        o.payment_status='refunded' if o.refund_amount==o.total else 'partially_refunded'
    if o.trip and o.trip.status=='offered':
        t=o.trip;t.pickups=[x for x in t.pickups if x['suborder_id']!=s.id];t.delivery_fee-=s.delivery_fee;t.cod_amount=max(0,t.cod_amount-s.total)
        if not t.pickups:t.status='cancelled';t.driver.available=True
    event(db,o,'rejected',f'{s.restaurant_name} declined: {reason or "Unable to prepare this order"}. {s.total:,} VND removed from the payable total.');refresh_status(db,o)

def cancel_order(db,o,reason,admin=False):
    if o.status=='cancelled':return
    if o.status=='delivered':fail('Delivered orders cannot be cancelled.',409)
    if not admin and (o.status not in {'awaiting_payment','payment_failed','pending','accepted'} or any(s.status in {'preparing','ready','picked_up','delivering','delivered'} for s in o.suborders) or (o.trip and o.trip.status in {'accepted','picking_up','delivering'})):
        fail('Preparation or delivery has started. Contact support to report a problem.',409)
    for s in o.suborders:
        if s.status!='rejected':s.status='cancelled'
    record_refund(db,o,o.total-o.refund_amount,reason or 'Order cancelled')
    o.refund_amount=o.total;o.status='cancelled'
    if o.payment_method=='online' and o.payment_status in {'paid','partially_refunded'}:o.payment_status='refunded'
    elif o.payment_method=='cod' or o.payment_status in {'pending','failed'}:o.payment_status='cancelled'
    for p in o.payments:
        if p.status=='pending':p.status='cancelled'
    if o.trip:
        o.trip.status='cancelled';o.trip.driver.available=True
    event(db,o,'cancelled',f'Order cancelled. {reason or "Customer requested cancellation"}'+(' Captured sandbox payment was refunded.' if o.payment_method=='online' and o.payment_status=='refunded' else ''))
