"""Idempotent weekly reconciliation in Vietnam local time, due Sunday 23:59."""
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from collections import defaultdict
from sqlalchemy import select
from models.entities import Order, SubOrder, Trip, Settlement, SettlementEntry, DispatchConfig, now
from services.commerce import config, iso

ZONE=ZoneInfo('Asia/Ho_Chi_Minh')

def aware(dt):return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
def period_for(dt):
    local=aware(dt).astimezone(ZONE)
    # A week is [Sunday 23:59, next Sunday 23:59). This matches the exact
    # scheduler cutoff and places the final minute of Sunday into the next run.
    start=datetime.combine(local.date()-timedelta(days=local.weekday()),time.min,tzinfo=ZONE)-timedelta(minutes=1)
    end=start+timedelta(days=7)
    if local>=end:start=end;end=start+timedelta(days=7)
    return start.astimezone(timezone.utc),end.astimezone(timezone.utc)

def settlement_json(s):
    return {k:getattr(s,k) for k in ['id','party_type','party_id','party_name','gross_amount','commission','cod_collected','amount','status']} | {'period_start':iso(s.period_start),'period_end':iso(s.period_end),'created_at':iso(s.created_at),'paid_at':iso(s.paid_at)}

def reconcile(db,include_current=False):
    # Serialize concurrent worker/scheduler runs in PostgreSQL. Unique source entries
    # additionally guarantee each completed restaurant order/trip is counted once.
    cfg=config(db);db.scalar(select(DispatchConfig).where(DispatchConfig.id==1).with_for_update())
    seen={(e.source_type,e.source_id) for e in db.scalars(select(SettlementEntry))}
    groups={};current=now()
    orders=list(db.scalars(select(Order).where(Order.status=='delivered',Order.delivered_at.is_not(None))))
    def add(start,end,ptype,pid,name,gross,commission,cod,source_type,source_id):
        if (source_type,source_id) in seen:return
        key=(start,ptype,pid)
        g=groups.setdefault(key,{'start':start,'end':end,'ptype':ptype,'pid':pid,'name':name,'gross':0,'commission':0,'cod':0,'entries':[]})
        g['gross']+=gross;g['commission']+=commission;g['cod']+=cod;g['entries'].append((source_type,source_id))
    for o in orders:
        start,end=period_for(o.delivered_at)
        if end>current and not include_current:continue
        for s in o.suborders:
            if s.status!='delivered':continue
            # Food-only receipts net of food-funded promotion; transport belongs to driver.
            food_discount=0 if o.promo_code=='FREESHIP' else s.discount
            gross=max(0,s.subtotal-food_discount);commission=round(gross*cfg.commission_rate)
            add(start,end,'restaurant',s.restaurant_id,s.restaurant_name,gross,commission,0,'suborder',s.id)
        t=o.trip
        if t and t.status=='delivered':
            add(start,end,'driver',t.driver_id,t.driver.user.name,t.delivery_fee,0,t.cod_collected,'trip',t.id)
    result=[]
    for g in groups.values():
        row=db.scalar(select(Settlement).where(Settlement.period_start==g['start'],Settlement.party_type==g['ptype'],Settlement.party_id==g['pid']))
        if row and row.status=='paid':
            # A paid period cannot acquire new deliveries: delivered_at fixes the
            # period and only completed periods may be marked paid.
            continue
        if not row:
            row=Settlement(period_start=g['start'],period_end=g['end'],party_type=g['ptype'],party_id=g['pid'],party_name=g['name'],gross_amount=0,commission=0,cod_collected=0,amount=0,status='pending');db.add(row);db.flush()
        row.gross_amount+=g['gross'];row.commission+=g['commission'];row.cod_collected+=g['cod'];row.amount=row.gross_amount-row.commission-row.cod_collected
        for source_type,source_id in g['entries']:db.add(SettlementEntry(settlement_id=row.id,source_type=source_type,source_id=source_id))
        result.append(row)
    db.flush();return result
