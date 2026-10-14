import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import select, update
import jwt
from .db import table, transaction
from .security import hash_password, verify_password, token_for, decode_token, refresh_hash

router=APIRouter(prefix='/api/auth',tags=['Авторизация'])
bearer=HTTPBearer(auto_error=False)

class Login(BaseModel):
    email:str=Field(min_length=3,max_length=254)
    password:str=Field(min_length=1,max_length=256)
class Refresh(BaseModel):
    refresh_token:str=Field(min_length=20,max_length=512)

def ok(data=None,message='Готово'):
    return {'success':True,'data':data,'message':message,'error_code':None}

def find_user(conn, ident=None, email=None):
    users,roles=table('Users'),table('Roles')
    query=select(users,roles.c.Code.label('Role')).join(roles,users.c.RoleId==roles.c.Id)
    query=query.where(users.c.Id==ident) if ident is not None else query.where(users.c.Email==email)
    row=conn.execute(query).mappings().first()
    return dict(row) if row else None

def public_user(user):
    return {'Id':user['Id'],'Email':user['Email'],'Name':' '.join(filter(None,[user['LastName'],user['FirstName'],user['Patronymic']])),'Role':user['Role'],'WorkshopId':user['WorkshopId'],'TeamId':user['TeamId']}

def current_user(credentials:HTTPAuthorizationCredentials=Depends(bearer)):
    try:
        if not credentials: raise ValueError()
        claims=decode_token(credentials.credentials)
        with transaction() as conn:
            user=find_user(conn,ident=int(claims['sub']))
            tokens=table('RefreshTokens')
            session=conn.execute(select(tokens.c.Id).where(tokens.c.UserId==int(claims['sub']),tokens.c.TokenHash==bytes.fromhex(claims['sid']),tokens.c.RevokedAt.is_(None),tokens.c.ExpiresAt>datetime.utcnow())).first()
            if not session: raise ValueError()
        if not user or not user['IsActive']: raise ValueError()
        return public_user(user)
    except (ValueError,KeyError,jwt.PyJWTError):
        raise HTTPException(401,'Войдите в систему заново.',headers={'WWW-Authenticate':'Bearer'})

def issue(conn,user):
    token=secrets.token_urlsafe(48)
    now=datetime.utcnow().replace(microsecond=0)
    conn.execute(table('RefreshTokens').insert().values(UserId=user['Id'],TokenHash=refresh_hash(token),CreatedAt=now,ExpiresAt=now+timedelta(days=7)))
    return {'access_token':token_for(user,refresh_hash(token).hex()),'refresh_token':token,'token_type':'bearer','expires_in':3600,'user':public_user(user)}

@router.post('/login')
def login(body:Login):
    with transaction() as conn:
        user=find_user(conn,email=body.email.strip().lower())
        if not user or not user['IsActive'] or not verify_password(body.password,user['PasswordHash']):
            raise HTTPException(401,'Неверный email или пароль.')
        return ok(issue(conn,user),'Вы вошли в систему.')

@router.post('/refresh')
def refresh(body:Refresh):
    with transaction() as conn:
        tokens=table('RefreshTokens')
        row=conn.execute(select(tokens).with_hint(tokens,'WITH (UPDLOCK, HOLDLOCK)',dialect_name='mssql').where(tokens.c.TokenHash==refresh_hash(body.refresh_token))).mappings().first()
        now=datetime.utcnow()
        if not row or row['RevokedAt'] or row['ExpiresAt']<=now: raise HTTPException(401,'Сессия истекла. Войдите снова.')
        user=find_user(conn,ident=row['UserId'])
        if not user or not user['IsActive']: raise HTTPException(401,'Учётная запись отключена.')
        conn.execute(update(tokens).where(tokens.c.Id==row['Id']).values(RevokedAt=now))
        return ok(issue(conn,user))

@router.post('/logout')
def logout(body:Refresh,user=Depends(current_user)):
    with transaction(user['Id']) as conn:
        t=table('RefreshTokens')
        conn.execute(update(t).where(t.c.UserId==user['Id'],t.c.TokenHash==refresh_hash(body.refresh_token)).values(RevokedAt=datetime.utcnow()))
    return ok(message='Вы вышли из системы.')

@router.get('/me')
def me(user=Depends(current_user)):
    return ok(user)

