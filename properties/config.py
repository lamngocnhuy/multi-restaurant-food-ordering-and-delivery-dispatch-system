"""Environment settings; PostgreSQL is the normal persistence engine."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg://localtable:localtable@localhost:5432/localtable')
SECRET_KEY = os.getenv('SECRET_KEY', 'development-only-change-this-secret-before-deploying-2026')
PAYMENT_SECRET = os.getenv('PAYMENT_WEBHOOK_SECRET', os.getenv('PAYMENT_CALLBACK_SECRET', 'development-payment-secret-change-in-production'))
APP_ENV = os.getenv('APP_ENV', 'development')
COOKIE_SECURE = os.getenv('SECURE_COOKIES', os.getenv('COOKIE_SECURE', 'false')).lower() == 'true'
SEED_DEMO = os.getenv('SEED_DEMO', 'true').lower() == 'true'
ENABLE_SCHEDULER = os.getenv('ENABLE_SCHEDULER', 'true').lower() == 'true'
PAYMENT_PROVIDER = os.getenv('PAYMENT_PROVIDER', 'sandbox')
DEMO_PASSWORD = os.getenv('DEMO_PASSWORD', 'Demo123!')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000').rstrip('/')
TRUSTED_HOSTS = [s.strip() for s in os.getenv('TRUSTED_HOSTS', 'localhost,127.0.0.1,testserver').split(',') if s.strip()]
if APP_ENV == 'production':
    if SECRET_KEY.startswith('development') or len(SECRET_KEY) < 32:
        raise RuntimeError('Production SECRET_KEY must be a random secret of at least 32 characters.')
    if PAYMENT_SECRET.startswith('development'):
        raise RuntimeError('Production PAYMENT_WEBHOOK_SECRET must be configured.')
    if not COOKIE_SECURE:
        raise RuntimeError('Production requires SECURE_COOKIES=true and an HTTPS reverse proxy.')
    if SEED_DEMO:
        raise RuntimeError('Disable SEED_DEMO in production.')
