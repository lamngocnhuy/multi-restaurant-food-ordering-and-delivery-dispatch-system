"""Repeatable development fixtures. No real payment credentials or card data."""
from sqlalchemy import select
from models.entities import User, Restaurant, MenuItem, Driver, DispatchConfig, Order, SubOrder, OrderItem, Trip, OrderEvent, now, uid
from utilities.security import hash_password
from properties.config import DEMO_PASSWORD
from datetime import timedelta

PHOTO='https://images.unsplash.com/'
def image(key):return PHOTO+key+'?auto=format&fit=crop&w=1000&q=85'

CATALOG=[
('r-saigon','Saigon Kitchen','Vietnamese','Comfort in every bowl. Slow-simmered broths, fresh herbs and the flavors of home.','42 Nguyễn Huệ, District 1',10.7745,106.7031,'photo-1559847844-5315695dadae',True,['Local favorite','Fresh daily'],[
('PHO','Signature beef phở','Rice noodles, 12-hour beef broth, tender brisket, fresh herbs.',69000,'photo-1582878826629-29b7ad1cdc43','Noodles'),
('BANHMI','Saigon bánh mì','Crisp baguette with grilled pork, pickles, pâté and chili.',39000,'photo-1559314809-0d155014e29e','Vietnamese'),
('BUN','Lemongrass pork bowl','Grilled lemongrass pork, rice vermicelli, crunchy vegetables.',65000,'photo-1547592180-85f173990554','Bowls'),
('ROLL','Fresh spring rolls','Rice paper rolls with prawns, herbs and peanut dipping sauce.',45000,'photo-1563245372-f21724e3856d','Sides')]),
('r-pizza','Pizza & Co.','Italian','Wood-fired, hand-stretched and made to share. A little Naples in the neighborhood.','18 Lê Thánh Tôn, District 1',10.7811,106.7024,'photo-1513104890138-7c749659a591',True,['Wood-fired','Family favorite'],[
('MARG','Classic Margherita','San Marzano tomato, fresh mozzarella, basil and olive oil.',129000,'photo-1574071318508-1cdbab80d002','Pizza'),
('PEPP','Pepperoni passion','Mozzarella, spicy pepperoni and our signature tomato sauce.',159000,'photo-1628840042765-356cda07504e','Pizza'),
('PASTA','Truffle mushroom pasta','Creamy tagliatelle with wild mushrooms and truffle oil.',119000,'photo-1473093295043-cdd812d0e601','Pasta'),
('SALAD','Burrata garden salad','Creamy burrata, heirloom tomatoes and garden greens.',89000,'photo-1515543904379-3d757afe72e4','Sides')]),
('r-green','The Green Bowl','Healthy','Good food, good energy. Colorful, nourishing bowls built with seasonal ingredients.','25 Nguyễn Thị Minh Khai, District 1',10.7860,106.6990,'photo-1512621776951-a57141f2eefd',True,['Plant-based','Feel good food'],[
('AVO','Avocado harvest bowl','Avocado, quinoa, roasted vegetables and tahini dressing.',79000,'photo-1511690743698-d9d85f2fbf38','Bowls'),
('SALMON','Teriyaki salmon bowl','Grilled salmon, brown rice, edamame and sesame.',119000,'photo-1510130387422-82bed34b37e9','Bowls'),
('KALE','Crunchy kale salad','Kale, apple, walnuts, cranberries and lemon dressing.',69000,'photo-1512621776951-a57141f2eefd','Salads'),
('SMOOTHIE','Mango sunshine smoothie','Mango, banana and coconut milk, blended fresh.',49000,'photo-1505252585461-04db1eb84625','Drinks')]),
('r-seoul','Seoul Table','Korean','Your favorite Korean comfort food, from sizzling rice bowls to perfectly crispy chicken.','76 Mạc Thị Bưởi, District 1',10.7740,106.7050,'photo-1498654896293-37aacf113fd9',False,['Comfort food','Spicy favorites'],[
('BIBIM','Rainbow bibimbap','Warm rice, marinated beef, vegetables, egg and gochujang.',89000,'photo-1498654896293-37aacf113fd9','Bowls'),
('CHICKEN','Korean crispy chicken','Double-fried chicken tossed in sweet spicy glaze.',99000,'photo-1562967914-608f82629710','Chicken'),
('KIMCHI','Kimchi fried rice','Wok-fried rice with aged kimchi and a sunny-side egg.',69000,'photo-1603133872878-684f208fb84b','Rice'),
('TOK','Cheesy tteokbokki','Chewy rice cakes in a rich spicy sauce with melted cheese.',79000,'photo-1635363638580-c2809d049eee','Sides')]),
('r-burger','Burger Theory','Burgers','Smash patties, proper buns, and absolutely no shortcuts. Your cravings, understood.','31 Pasteur, District 1',10.7730,106.7000,'photo-1568901346375-23c9450c58cd',False,['Smash burgers','American'],[
('CLASSIC','The classic smash','Double beef patty, cheddar, pickles and house sauce.',89000,'photo-1568901346375-23c9450c58cd','Burgers'),
('CHICK','Crispy chicken burger','Buttermilk chicken, slaw and spicy mayo.',79000,'photo-1606755962773-d324e0a13086','Burgers'),
('FRIES','Loaded cheese fries','Golden fries, cheese sauce and crispy onions.',49000,'photo-1573080496219-bb080dd4f877','Sides'),
('SHAKE','Chocolate milkshake','Thick chocolate shake with real vanilla ice cream.',55000,'photo-1572490122747-3968b75cc699','Drinks')]),
('r-sushi','Mori Sushi','Japanese','Small details, beautiful flavors. Freshly rolled sushi and warm Japanese classics.','15 Thái Văn Lung, District 1',10.7800,106.7050,'photo-1579871494447-9811cf80d66c',False,['Fresh sushi','Japanese'],[
('MAKI','Salmon avocado roll','Fresh salmon and avocado, rolled with sushi rice.',99000,'photo-1579871494447-9811cf80d66c','Sushi'),
('SUSHI','Chef’s sushi selection','Eight handcrafted pieces of the chef’s daily favorites.',169000,'photo-1553621042-f6e147245754','Sushi'),
('RAMEN','Tonkotsu ramen','Rich pork broth, springy noodles, chashu and soft egg.',119000,'photo-1569718212165-3a8278d5f624','Noodles'),
('GYOZA','Pan-fried gyoza','Six golden pork dumplings with a citrus dipping sauce.',59000,'photo-1563245372-f21724e3856d','Sides')]),
('r-tea','Cloud Nine Tea','Drinks','A little happiness in a cup. Premium tea leaves, fresh fruit and chewy brown sugar pearls.','8 Đồng Khởi, District 1',10.7738,106.7045,'photo-1558857563-b371033873b8',False,['Bubble tea','Fresh brewed'],[
('MILK','Brown sugar pearl milk tea','Black tea, fresh milk and warm brown sugar pearls.',49000,'photo-1558857563-b371033873b8','Milk tea'),
('PEACH','Peach jasmine tea','Fragrant jasmine tea with fresh peach and citrus.',45000,'photo-1544145945-f90425340c7e','Fruit tea'),
('MATCHA','Strawberry matcha latte','Ceremonial matcha, strawberry purée and creamy milk.',59000,'photo-1515823064-d6e0c04616a7','Matcha'),
('COFFEE','Vietnamese iced coffee','Slow-dripped Vietnamese coffee with condensed milk.',35000,'photo-1461023058943-07fcbe16d735','Coffee')]),
('r-bakery','Butter & Crumb','Bakery','Fresh from the oven, made with patience. Buttery pastries and little everyday treats.','64 Lý Tự Trọng, District 1',10.7770,106.6980,'photo-1509440159596-0249088772ff',False,['Fresh baked','Sweet treats'],[
('CROISS','Butter croissant','Flaky, golden and made with cultured French butter.',39000,'photo-1555507036-ab1f4038808a','Pastries'),
('CAKE','Strawberry cloud cake','Vanilla sponge, fresh strawberries and whipped cream.',59000,'photo-1464305795204-6f5bbfc7fb81','Desserts'),
('COOKIE','Chocolate chunk cookies','Two soft-baked cookies with generous dark chocolate.',35000,'photo-1499636136210-6f4ee915583e','Desserts'),
('TART','Portuguese egg tart','Crispy pastry filled with silky caramelized custard.',29000,'photo-1488477181946-6428a0291777','Pastries')])]

def seed(db):
    if not db.get(DispatchConfig,1):db.add(DispatchConfig(id=1))
    roles=[('u-customer','customer','Alex Nguyen','customer@localtable.vn'),('u-admin','admin','Gather Admin','admin@localtable.vn'),('u-driver','driver','Minh Tran','driver@localtable.vn'),('u-driver2','driver','Linh Pham','driver2@localtable.vn')]
    for id_,role,name,email in roles:
        if not db.get(User,id_):db.add(User(id=id_,role=role,name=name,email=email,phone='0901234567',password_hash=hash_password(DEMO_PASSWORD),active=True))
    db.flush()
    if not db.get(Driver,'u-driver'):db.add(Driver(id='u-driver',online=True,available=True,lat=10.7750,lng=106.7020,last_location_at=now()))
    if not db.get(Driver,'u-driver2'):db.add(Driver(id='u-driver2',online=True,available=True,lat=10.7830,lng=106.6980,last_location_at=now()))
    for i,(rid,name,cat,desc,address,lat,lng,pic,featured,tags,dishes) in enumerate(CATALOG):
        owner='u-restaurant' if i==0 else f'u-restaurant-{i}'
        if not db.get(User,owner):db.add(User(id=owner,role='restaurant',name=name+' Team',email='restaurant@localtable.vn' if i==0 else f'restaurant{i+1}@localtable.vn',phone='0902345678',password_hash=hash_password(DEMO_PASSWORD),active=True))
        db.flush()
        if not db.get(Restaurant,rid):db.add(Restaurant(id=rid,owner_id=owner,name=name,category=cat,description=desc,address=address,lat=lat,lng=lng,image=image(pic),featured=featured,tags=tags,delivery_minutes=20+i*2,accepting_orders=True))
        db.flush()
        for j,(code,title,description,price,photo,category) in enumerate(dishes):
            mid=f'{rid}-{code.lower()}'
            options={'sizes':[{'name':'Regular','price':0},{'name':'Large','price':15000}],'toppings':[{'name':'Extra egg','price':10000},{'name':'Extra protein','price':20000}]} if cat!='Drinks' and category not in ('Drinks','Desserts','Pastries') else {'sizes':[{'name':'Regular','price':0},{'name':'Large','price':10000}],'sugar':['100%','70%','50%','0%'],'ice':['Regular','Less ice','No ice'],'toppings':[{'name':'Brown sugar pearls','price':10000},{'name':'Milk foam','price':12000}]} if cat=='Drinks' or category=='Drinks' else {}
            if not db.get(MenuItem,mid):db.add(MenuItem(id=mid,restaurant_id=rid,code=code,name=title,description=description,category=category,price=price,image=image(photo),available=True,popular=j==0,options=options))
    db.flush()
    # A finished previous-week order makes history, reviews and reconciliation reviewable.
    if not db.scalar(select(Order).where(Order.code=='GT-DEMO001')):
        dt=now()-timedelta(days=8)
        o=Order(id='o-demo-delivered',code='GT-DEMO001',customer_id='u-customer',idempotency_key='seed-delivered-001',status='delivered',payment_method='cod',payment_status='collected',subtotal=108000,delivery_fee=16000,discount=10800,total=113200,refund_amount=0,address='22 Nguyễn Huệ, District 1, Ho Chi Minh City',lat=10.7756,lng=106.7033,phone='0901234567',note='',promo_code='WELCOME10',created_at=dt,delivered_at=dt+timedelta(minutes=31));db.add(o);db.flush()
        s=SubOrder(id='s-demo-delivered',order_id=o.id,restaurant_id='r-saigon',restaurant_name='Saigon Kitchen',address='42 Nguyễn Huệ, District 1',lat=10.7745,lng=106.7031,status='delivered',subtotal=108000,delivery_fee=16000,discount=10800,total=113200);db.add(s);db.flush()
        db.add(OrderItem(suborder_id=s.id,menu_item_id='r-saigon-pho',name='Signature beef phở',quantity=1,options={'size':'Regular','toppings':[]},note='',unit_price=69000,line_total=69000))
        db.add(OrderItem(suborder_id=s.id,menu_item_id='r-saigon-banhmi',name='Saigon bánh mì',quantity=1,options={'size':'Regular','toppings':[]},note='',unit_price=39000,line_total=39000))
        db.add(Trip(id='t-demo-delivered',code='TR-DEMO001',order_id=o.id,driver_id='u-driver',status='delivered',pickups=[{'suborder_id':s.id,'restaurant_name':'Saigon Kitchen','address':s.address,'lat':s.lat,'lng':s.lng,'picked_up':True,'sequence':1}],declined_driver_ids=[],delivery_fee=16000,cod_amount=113200,cod_collected=113200,created_at=dt,completed_at=o.delivered_at))
        for minutes,status,msg in [(0,'pending','Order placed with Saigon Kitchen.'),(2,'accepted','Saigon Kitchen accepted your order.'),(12,'preparing','Your food is being prepared.'),(22,'picking_up','Minh is collecting your food.'),(26,'delivering','Your food is on the way.'),(31,'delivered','Delivered. Enjoy your meal!')]:db.add(OrderEvent(order_id=o.id,status=status,message=msg,created_at=dt+timedelta(minutes=minutes)))
    db.commit()
