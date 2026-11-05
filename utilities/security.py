import base64
import hashlib
import hmac
import json
import os
import time
from properties.config import SECRET_KEY

def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return 'scrypt$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(digest).decode()

def check_password(password, stored):
    try:
        _, salt, digest = stored.split('$')
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(actual, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False

def token_for(user_id):
    body = base64.urlsafe_b64encode(json.dumps({'sub':user_id,'exp':int(time.time())+604800}).encode()).decode().rstrip('=')
    sig = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
    return body + '.' + sig

def read_token(token):
    try:
        body, sig = token.rsplit('.',1)
        if not hmac.compare_digest(hmac.new(SECRET_KEY.encode(),body.encode(),hashlib.sha256).hexdigest(),sig): return None
        data=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
        return data['sub'] if data['exp'] > time.time() else None
    except Exception:
        return None
