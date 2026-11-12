# LOCAL table API contract

All API routes use JSON, same origin, session cookie. Errors are `{detail:"Actionable message"}` (validation can be array). IDs are strings. Money is integer VND. All dates ISO UTC. Register creates customers only. Demo accounts: `customer@localtable.vn`, `restaurant@localtable.vn`, `driver@localtable.vn`, `admin@localtable.vn`; password `Demo123!` (override via DEMO_PASSWORD). Restaurant account owns restaurant `r-saigon`.

## Session
- GET `/api/auth/me`: `{user:null|{id,name,email,role,phone,restaurant_id}, demo_mode:boolean}`.
- POST `/api/auth/login` `{email,password}` -> `{user}`. POST `/api/auth/register` `{name,email,password,phone?}` -> `{user}`. POST `/api/auth/logout`.

## Catalog (customer)

All catalog list, search, and detail routes require an active customer session. Guests receive `401` and staff receive `403`. Restaurant accounts manage their own menus through the restaurant workspace API.

- GET `/api/restaurants?q=&category=` -> `{restaurants:[{id,name,description,category,image,address,lat,lng,rating,review_count,delivery_minutes,accepting_orders,delivery_fee,featured,tags}]}`.
- GET `/api/restaurants/{id}` -> `{restaurant:... ,menu:[{id,restaurant_id,code,name,description,category,price,image,available,popular,options:{sizes:[{name,price}],sugar:[string],ice:[string],toppings:[{name,price}]}}]}`.
- GET `/api/menu?q=&category=&restaurant_id=` -> `{items:[dish with restaurant_name]}`. GET `/api/menu/{id}` -> `{item}`.

## Cart and checkout (customer)

Customers enter their street address. Coordinates are used to estimate delivery fees and are submitted separately from the address text. The server does not look up addresses from coordinates.

- GET `/api/cart` -> `{items:[{id,menu_item_id,restaurant_id,restaurant_name,name,image,quantity,options:{size,sugar,ice,toppings:[]},note,base_price,extra_price,unit_price,line_total,available}],groups:[{restaurant_id,restaurant_name,items,subtotal}],subtotal,item_count}`.
- POST `/api/cart/items` `{menu_item_id,quantity:1,options:{size?,sugar?,ice?,toppings:[]},note:""}` -> full cart.
- PATCH `/api/cart/items/{id}` `{quantity?,options?,note?}` -> cart. DELETE same -> cart. DELETE `/api/cart` -> cart.
- POST `/api/cart/quote` `{address,lat:10.7769,lng:106.7009,promo_code?:"WELCOME10"}` -> `{subtotal,delivery_fee,discount,total,groups:[{restaurant_id,restaurant_name,subtotal,delivery_fee,discount,total,distance_km}],promo_code}`. WELCOME10 takes 10% food subtotal up to 50000; FREESHIP up to 30000 delivery.
- POST `/api/orders` `{address,lat,lng,phone,note?,payment_method:"cod"|"online",promo_code?,idempotency_key:"unique browser UUID"}` -> `{order,... payment_url?:"/payment/{payment_id}"}`. Cart clears once. Online sandbox pending until callback; no card input.
- GET `/api/orders` -> `{orders:[order]}`. GET `/api/orders/{id}` -> `{order}`. Order fields: id,code,status,payment_method,payment_status,subtotal,delivery_fee,discount,total,refund_amount,payable_total,address,lat,lng,phone,note,created_at,delivered_at,customer:{name,phone},suborders:[{id,restaurant_id,restaurant_name,address,lat,lng,status,subtotal,delivery_fee,discount,total,items:[{name,quantity,options,note,unit_price,line_total}]}],trip:null|{id,code,status,driver:{name,phone,lat,lng,last_location_at},pickups:[{suborder_id,restaurant_name,address,lat,lng,picked_up,sequence}],delivery_fee,cod_amount},events:[{id,status,message,created_at}],reviews:[{id,target_type,target_id,rating,comment}],can_review.
- POST `/api/orders/{id}/cancel` `{reason}` permitted before preparation/pickup; automatic refund bookkeeping.
- GET `/api/payments/{id}` -> `{payment:{id,order_id,amount,status,provider,checkout_url}}`. POST `/api/payments/{id}/sandbox` `{outcome:"success"|"failure"}` -> `{order}` (owner only, sandbox only); failure allows retry. POST `/api/orders/{id}/retry-payment` -> `{payment_url,payment}`.
- POST `/api/orders/{id}/reviews` `{target_type:"restaurant"|"driver",target_id,rating:1..5,comment}` delivered owned order only, once per target.

## Restaurant workspace
- GET `/api/restaurant/dashboard` -> `{restaurant,stats:{orders_today,revenue_today,pending_orders,total_orders},orders:[order],menu:[dish]}`. GET `/api/restaurant/orders` -> `{orders}`.
- POST `/api/restaurant/menu` `{code,name,description,category,price,image,available,popular?,options?}` -> `{item}`. PATCH `/api/restaurant/menu/{id}` same optional fields. DELETE only dishes without historical orders and not temporarily unavailable.
- PATCH `/api/restaurant/profile` `{accepting_orders:boolean}` -> `{restaurant}`.
- POST `/api/restaurant/suborders/{id}/status` `{status:"accepted"|"rejected"|"preparing"|"ready",reason?}` -> `{order}`. One restaurant rejection credits only that suborder; remaining orders continue.

## Driver workspace
- GET `/api/driver/dashboard` -> `{driver:{id,name,phone,online,available,lat,lng,last_location_at},stats:{completed_trips,earnings,total_cod},trips:[order],history:[order]}`.
- POST `/api/driver/status` `{online:boolean}` -> `{driver}`.
- POST `/api/driver/location` `{lat,lng}` -> `{driver}`. Frontend send at most every 10 seconds while active and poll tracking every 5–10 seconds; show stale positions after 20 seconds.
- POST `/api/driver/trips/{trip_id}/accept` -> `{order}`; `/decline` `{reason?}` -> `{order}` automatically finds another available online driver; `/pickup` `{suborder_id}` requires current first uncollected stop ready; `/complete` `{cod_received:boolean}` requires all pickups (true for COD); `/incident` `{reason}` marks incident and notifies admin (customer unavailable cancels/refunds under admin action).

## Admin and reports
- GET `/api/admin/dashboard` -> `{stats:{total_orders,active_orders,revenue,total_customers,online_drivers,pending_settlements},orders:[order],users:[user plus active],drivers:[driver],config:{max_group_distance_km,dispatch_radius_km,base_delivery_fee,per_km_fee,commission_rate},settlements:[settlement]}`.
- GET `/api/reports?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD` (admin or restaurant) -> `{summary:{total_orders,completed_orders,gross_revenue,food_revenue,delivery_fees,discounts,refunds,commission,net_revenue},daily:[{date,orders,revenue}],orders:[order]}`.
- PATCH `/api/admin/users/{id}` `{active:boolean}`. PATCH `/api/admin/config` configuration fields.
- POST `/api/admin/orders/{id}/dispatch` -> `{order}`. POST `/api/admin/orders/{id}/resolve` `{action:"cancel"|"retry_dispatch",reason}`.
- GET `/api/admin/settlements` -> `{settlements}`. POST `/api/admin/settlements/run` `{}` reconciles due Sunday23:59 Asia/Ho_Chi_Minh periods idempotently (manual processing also available for completed current period with `{include_current:true}`). POST `/api/admin/settlements/{id}/paid` -> `{settlement}`. Settlement fields id,period_start,period_end,party_type,party_id,party_name,gross_amount,commission,cod_collected,amount,status,created_at.

The HTML entry at `/` or `/sign-in` shows a standalone sign-in form when signed out. After customer sign-in, `/order` opens ordering (`/#explore` still works). Customer pages include `/restaurants/{id}`, `/orders`, `/orders/{id}`, and `/payment/{id}`. The staff workspaces are `/restaurant`, `/driver`, and `/admin`. A signed-out request to any app page receives the sign-in form; a signed-in request to another role's page redirects to the account's own home. Docs at `/docs`; health `/health`. Call `/api/auth/me` before loading the catalog and request it only for a customer session. Config public info: GET `/api/config`.

Admin account provisioning: POST `/api/admin/users` with `{name,email,password,phone?,role:"customer"|"restaurant"|"driver"|"admin",restaurant?:{name,description?,category,address,lat,lng,image?}}` -> `{user}` (201). Restaurant details required only for restaurant role; newly provisioned restaurants start closed until their menu is ready. Other create endpoints also use 201. Demo second driver `driver2@localtable.vn` / `Demo123!` allows decline-and-reassign. Unreviewed restaurants return `rating:null,review_count:0` (show “New”). Production initial admin: `python scripts/create_user.py --email ... --name ... --role admin` prompts for a password. Signed callback `/api/payments/callback` exact JSON `{payment_id,outcome,external_reference}` plus `X-Payment-Signature` HMAC-SHA256 hex over the exact request body, using PAYMENT_WEBHOOK_SECRET. This is a provider integration boundary, not a live processor integration.

Unanswered driver offers expire after 60 seconds; the 30-second background sweep releases the reservation and tries another eligible online driver (typically 60–90 seconds). The offer timestamp resets when reassigned. Completed delivery timestamps serialize with reconciliation to avoid stranding a trip across the Sunday cutoff.
