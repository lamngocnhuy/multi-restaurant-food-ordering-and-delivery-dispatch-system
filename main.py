"""Gather — multi-restaurant ordering and delivery dispatch."""
import asyncio
import hashlib
import logging
from contextlib import asynccontextmanager, suppress
from urllib.parse import urlparse
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from database.connection import Base, engine, get_db, SessionLocal
from models.entities import User
from properties.config import ROOT, SEED_DEMO, ENABLE_SCHEDULER, TRUSTED_HOSTS, APP_ENV
from api.routes import router
from services.seed import seed
from services.reconciliation import reconcile
from services.commerce import retry_waiting_dispatch
from utilities.security import read_token

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
log=logging.getLogger('gather')

def scheduled_work():
    with SessionLocal() as db:
        try:
            reconcile(db)
            db.commit()  # Release accounting lock before dispatch takes order locks.
            retry_waiting_dispatch(db)
            db.commit()
        except Exception:
            db.rollback();log.exception('Scheduled reconciliation / dispatch retry failed')

async def scheduler():
    while True:
        await asyncio.sleep(30)
        await asyncio.to_thread(scheduled_work)

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if SEED_DEMO:seed(db)
        else:
            from services.commerce import config
            config(db);db.commit()
    task=asyncio.create_task(scheduler()) if ENABLE_SCHEDULER else None
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):await task
    engine.dispose()

app=FastAPI(title='Gather | Food ordering & delivery dispatch',version='1.0.0',description='Multi-restaurant ordering, restaurant operations, delivery dispatch and weekly reconciliation. Monetary amounts are integer VND. Online payments run in an explicitly labelled sandbox.',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=TRUSTED_HOSTS)

@app.middleware('http')
async def browser_security(request:Request,call_next):
    # Cookies are SameSite=Lax. Origin checks also protect same-site sibling hosts.
    # Payment providers authenticate callbacks with HMAC over the exact body.
    if request.method in {'POST','PUT','PATCH','DELETE'} and request.url.path!='/api/payments/callback':
        origin=request.headers.get('origin')
        if origin:
            parsed=urlparse(origin)
            if parsed.netloc.lower()!=request.headers.get('host','').lower() or parsed.scheme not in {'http','https'}:
                return JSONResponse({'detail':'Request origin does not match this website. Reload this page and try again.'},status_code=403)
        if request.headers.get('sec-fetch-site')=='cross-site':
            return JSONResponse({'detail':'Cross-site requests are not allowed.'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Permissions-Policy']='geolocation=(self), camera=(), microphone=()'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://unpkg.com; img-src 'self' data: https:; font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net; connect-src 'self'; frame-src https://www.openstreetmap.org; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    if request.url.path.startswith('/api') or request.url.path.startswith('/payment'):response.headers['Cache-Control']='no-store'
    if APP_ENV=='production':response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    return response

@app.exception_handler(IntegrityError)
async def integrity_error(request,exc):
    log.warning('database_constraint path=%s constraint=%s',request.url.path,type(exc.orig).__name__)
    return JSONResponse({'detail':'This action conflicts with an existing record or another update. Refresh and try again.'},status_code=409)

app.include_router(router)
app.mount('/static',StaticFiles(directory=str(ROOT/'asset')),name='static')
app.mount('/asset',StaticFiles(directory=str(ROOT/'asset')),name='asset')
templates=Jinja2Templates(directory=str(ROOT/'controls'))
ROLE_HOME = {'customer': '/order', 'restaurant': '/restaurant', 'driver': '/driver', 'admin': '/admin'}
CUSTOMER_PAGES = {'order', 'explore', 'restaurants', 'orders', 'reviews', 'payment'}
NO_STORE = {'Cache-Control': 'no-store'}


def page_user(request: Request, db=Depends(get_db)):
    """Resolve the session before choosing which HTML to send."""
    user_id = read_token(request.cookies.get('gather_session', ''))
    user = db.get(User, user_id) if user_id else None
    return user if user and user.active and user.role in ROLE_HOME else None


def web_page(request: Request, template: str):
    # Give related HTML, scripts and styles one revision so an older cached app
    # script cannot boot against the new markup and authorization rules.
    version = hashlib.blake2b(digest_size=8)
    for name in ('app.js', 'auth.js', 'style.css'):
        version.update((ROOT / 'asset' / name).read_bytes())
    return templates.TemplateResponse(request=request, name=template, headers=NO_STORE, context={
        'asset_version': version.hexdigest(),
        'demo_mode': SEED_DEMO and APP_ENV != 'production',
    })

@app.get('/health')
def health():
    with SessionLocal() as db:db.execute(text('SELECT 1'))
    return {'status':'ok','service':'Gather','database':'connected'}

@app.get('/sign-in', include_in_schema=False)
def sign_in(request: Request, user=Depends(page_user)):
    if user:
        return RedirectResponse(ROLE_HOME[user.role], status_code=303, headers=NO_STORE)
    return web_page(request, 'sign_in.html')


@app.get('/',include_in_schema=False)
@app.get('/order', include_in_schema=False)
@app.get('/explore', include_in_schema=False)
@app.get('/restaurants/{path:path}',include_in_schema=False)
@app.get('/orders',include_in_schema=False)
@app.get('/orders/{path:path}',include_in_schema=False)
@app.get('/reviews', include_in_schema=False)
@app.get('/restaurant',include_in_schema=False)
@app.get('/driver',include_in_schema=False)
@app.get('/admin',include_in_schema=False)
@app.get('/payment/{path:path}',include_in_schema=False)
def shell(request: Request, user=Depends(page_user)):
    if not user:
        return web_page(request, 'sign_in.html')

    section = request.url.path.strip('/').split('/', 1)[0]
    if (section in CUSTOMER_PAGES and user.role != 'customer') or (
        section in {'restaurant', 'driver', 'admin'} and section != user.role
    ):
        return RedirectResponse(ROLE_HOME[user.role], status_code=303, headers=NO_STORE)
    return web_page(request, 'index.html')
