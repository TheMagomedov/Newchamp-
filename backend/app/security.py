import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
import jwt
from . import config

def hash_password(password):
    if len(password) < 8 or not any(c.isdigit() for c in password) or not any(c.isalpha() for c in password):
        raise ValueError('Пароль: минимум 8 символов, буквы и цифры.')
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600_000)
    return 'pbkdf2_sha256$600000$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(key).decode()

def verify_password(password, stored):
    try:
        kind, rounds, salt, expected = stored.split('$')
        if kind != 'pbkdf2_sha256' or int(rounds) > 1_000_000:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), base64.b64decode(salt), int(rounds))
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False

def token_for(user,session_id):
    if len(config.SECRET) < 32:
        raise RuntimeError('Выполните scripts/setup.py для создания локального секрета.')
    now = datetime.now(timezone.utc)
    return jwt.encode({'sub':str(user['Id']), 'sid':session_id, 'iat':now, 'exp':now+timedelta(hours=1), 'iss':'toir-prof', 'aud':'toir-clients'},config.SECRET,algorithm='HS256')

def decode_token(token):
    return jwt.decode(token,config.SECRET,algorithms=['HS256'],audience='toir-clients',issuer='toir-prof',options={'require':['exp','sub','iat','sid']})

def refresh_hash(token):
    return hashlib.sha256(token.encode()).digest()

