"""Общие операции API: идемпотентность, поиск и подписи связанных записей."""
import hashlib
import json
import re
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select,func,or_,text
from .db import table,transaction
from .querying import clauses


def mutation(request,user,payload,operation):
    key=request.headers.get('Idempotency-Key')
    if key and (len(key)>100 or len(key)<8): raise HTTPException(400,'Некорректный Idempotency-Key.')
    fingerprint=hashlib.sha256((request.method+request.url.path+json.dumps(jsonable_encoder(payload),sort_keys=True,ensure_ascii=False)).encode()).hexdigest()
    with transaction(user['Id']) as conn:
        if key:
            lock=hashlib.sha256(f"{user['Id']}:{key}".encode()).hexdigest()
            result=conn.execute(text("DECLARE @r int; EXEC @r=sys.sp_getapplock @Resource=:r,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000; SELECT @r"),{'r':'request:'+lock}).scalar()
            if result<0: raise HTTPException(409,'Операция уже выполняется. Повторите с тем же ключом.')
            saved=conn.execute(text('SELECT Fingerprint,Response FROM dbo.ClientRequests WHERE UserId=:u AND RequestKey=:k'),{'u':user['Id'],'k':key}).mappings().first()
            if saved:
                if saved['Fingerprint']!=fingerprint: raise HTTPException(409,'Ключ уже использован для другого запроса.')
                return json.loads(saved['Response'])
        result=operation(conn)
        if key:
            conn.execute(text('INSERT dbo.ClientRequests(UserId,RequestKey,Fingerprint,Response) VALUES(:u,:k,:f,:r)'),{'u':user['Id'],'k':key,'f':fingerprint,'r':json.dumps(jsonable_encoder(result),ensure_ascii=False)})
        return result


def filters(t,user,search='',status=None,workshop_id=None,**extra):
    conditions=clauses(t,user,workshop_id=workshop_id,**extra)
    if search:
        cols=[c for c in t.c if c.name in ('Name','Number','InventoryNumber','Code','Email','Description','LastName','FirstName','Patronymic','Model')]
        alternatives=[c.contains(search,autoescape=True) for c in cols]
        if t.name in ('WorkOrders','Users'):
            users=table('Users')
            full_name=func.concat(users.c.LastName,' ',users.c.FirstName,' ',func.coalesce(users.c.Patronymic,''))
            match=full_name.contains(search,autoescape=True)
            alternatives.append(t.c.MasterId.in_(select(users.c.Id).where(match)) if t.name=='WorkOrders' else match)
        if t.name=='WorkOrders':
            number=re.fullmatch(r'(?:Z-)?(\d{4})-(\d+)',search.strip(),re.IGNORECASE)
            if number and len(number[2])<=18:
                alternatives.append((func.year(t.c.CreatedAt)==int(number[1])) & (t.c.SequenceNumber==int(number[2])))
            elif search.isdigit() and len(search)<=18:
                alternatives.append(t.c.SequenceNumber==int(search))
        if alternatives: conditions.append(or_(*alternatives))
    if status and 'Status' in t.c: conditions.append(t.c.Status==status)
    return conditions

def enrich(conn,name,rows):
    maps={}
    for field,ref,label in [('EquipmentId','Equipment','EquipmentName'),('WorkshopId','Workshops','WorkshopName'),('TeamId','Teams','TeamName'),('MaintenanceTypeId','MaintenanceTypes','MaintenanceTypeName')]:
        ids={r[field] for r in rows if r.get(field) is not None}
        if ids:
            t=table(ref); maps[field]=(label,dict(conn.execute(select(t.c.Id,t.c.Name).where(t.c.Id.in_(ids))).tuples().all()))
    for row in rows:
        for field,(label,mapping) in maps.items(): row[label]=mapping.get(row.get(field))
    return rows
