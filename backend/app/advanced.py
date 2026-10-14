"""Поиск, уведомления и SSE; плановые операции подключаются из workflows."""
import asyncio
import hashlib
import json
import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, cast, String
from starlette.concurrency import run_in_threadpool
from .auth import bearer, current_user, ok
from .db import table, transaction
from .resources import RESOURCES, scope, public
from .api import detail
from .api_shared import filters
from .workflows import (
    router as workflow_router, upcoming, overdue, schedule_window,
    create_schedule_order, complete_order,
)

router = APIRouter(prefix='/api', tags=['Планирование и события'])
router.include_router(workflow_router)


@router.get('/equipment/{ident}/details')
def equipment_details(ident:int,user=Depends(current_user)):
    return detail('equipment',ident,user)


@router.get('/equipment/{ident}/related')
def equipment_related(ident:int,user=Depends(current_user)):
    data = detail('equipment',ident,user)['data']
    return ok({key:data[key] for key in ('orders','schedule','history')})


@router.get('/search')
@router.get('/global-search')
def search(q:str=Query(...,min_length=1,max_length=150),limit:int=Query(20,ge=1,le=100),user=Depends(current_user)):
    items,total = [],0
    with transaction(user['Id']) as conn:
        keys=['equipment','work-orders','materials','teams','schedule']
        if user['Role']=='admin': keys.append('users')
        for key in keys:
            name,label,_ = RESOURCES[key]
            t = table(name)
            conditions = filters(t,user,search=q)
            if key=='schedule':
                e = table('Equipment')
                conditions.append(t.c.EquipmentId.in_(select(e.c.Id).where(e.c.Name.contains(q,autoescape=True))))
            total += conn.execute(select(func.count()).select_from(t).where(*conditions)).scalar_one()
            for row in conn.execute(select(t).where(*conditions).order_by(t.c.Id.desc()).limit(limit)).mappings():
                data = public(row)
                title = data.get('Name') or data.get('DisplayNumber') or data.get('Number') or f"ТО №{row['Id']}"
                subtitle = data.get('InventoryNumber') or data.get('Description') or data.get('Code') or label
                if key=='users':
                    title=' '.join(str(data.get(field) or '') for field in ('LastName','FirstName','Patronymic')).strip()
                    subtitle=data['Email']
                items.append({'resource':key,'id':row['Id'],'label':title,'subtitle':str(subtitle)[:180]})
    return ok({'items':items[:limit],'total':total})


def notification_items(user):
    items = []
    now = datetime.utcnow()
    with transaction(user['Id']) as conn:
        orders,schedule,materials = table('WorkOrders'),table('MaintenanceSchedule'),table('Materials')
        rows = conn.execute(select(orders).where(*scope(orders,user),orders.c.Status.not_in(['выполнена','закрыта','отменена']))).mappings()
        for row in rows:
            if row['PlannedEnd'] < now:
                items.append({'id':f"order-overdue:{row['Id']}",'kind':'overdue','severity':'danger','title':'Заявка просрочена',
                    'message':public(row)['DisplayNumber'],'resource':'work-orders','entity_id':row['Id']})
            if row['TeamId'] is None:
                items.append({'id':f"order-unassigned:{row['Id']}",'kind':'unassigned','severity':'warning','title':'Не назначена бригада',
                    'message':public(row)['DisplayNumber'],'resource':'work-orders','entity_id':row['Id']})
        for row in conn.execute(select(schedule).where(*scope(schedule,user),schedule.c.PlannedAt<now,
                schedule.c.Status.not_in(['выполнено','отменено']))).mappings():
            items.append({'id':f"schedule-overdue:{row['Id']}",'kind':'schedule_overdue','severity':'warning','title':'Просрочено плановое ТО',
                'message':f"Плановая дата: {row['PlannedAt'].isoformat()}",'resource':'schedule','entity_id':row['Id']})
        for row in conn.execute(select(materials).where(materials.c.Stock<=materials.c.MinimumStock)).mappings():
            items.append({'id':f"low-stock:{row['Id']}",'kind':'low_stock','severity':'warning','title':'Низкий остаток материала',
                'message':f"{row['Name']}: {row['Stock']} {row['Unit']}",'resource':'materials','entity_id':row['Id']})
    return {'items':items,'total':len(items)}


@router.get('/notifications')
def notifications(user=Depends(current_user)):
    return ok(notification_items(user))


def revision_state(user):
    """Audit watermarks only for rows visible to this principal; secret fields never read."""
    state = {}
    audit = table('AuditLog')
    with transaction(user['Id']) as conn:
        for key,(name,_,_) in RESOURCES.items():
            if key=='users' and user['Role']!='admin': continue
            t = table(name)
            conditions = filters(t,user)
            count, last_id = conn.execute(select(func.count(),func.max(t.c.Id)).where(*conditions)).one()
            last_change = conn.execute(select(func.max(audit.c.Id)).where(audit.c.Entity==name,
                audit.c.EntityId.in_(select(cast(t.c.Id,String(80))).where(*conditions)))).scalar()
            state[key] = [count,last_id,last_change]
        # Material line edits also change Materials.Stock, so their audit is included above.
    revision = hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
    return revision,state


def sse_event(kind,data):
    return f"event: {kind}\ndata: {json.dumps(jsonable_encoder(data),ensure_ascii=False)}\n\n"


async def event_stream(request,user,credentials,poll_seconds=2,heartbeat_seconds=15):
    previous_revision,previous_state = await run_in_threadpool(revision_state,user)
    yield sse_event('revision',{'revision':previous_revision,'changed_resources':list(previous_state)})
    last_heartbeat = time.monotonic()
    while not await request.is_disconnected():
        await asyncio.sleep(poll_seconds)
        try:
            fresh_user = await run_in_threadpool(current_user,credentials)
        except HTTPException:
            yield sse_event('auth_expired',{'message':'Сессия истекла. Войдите снова.'})
            return
        revision,state = await run_in_threadpool(revision_state,fresh_user)
        if revision != previous_revision:
            changed = [key for key in set(state)|set(previous_state) if state.get(key)!=previous_state.get(key)]
            yield sse_event('revision',{'revision':revision,'changed_resources':sorted(changed)})
            previous_revision,previous_state = revision,state
        if time.monotonic()-last_heartbeat >= heartbeat_seconds:
            yield sse_event('heartbeat',{'time':datetime.utcnow().isoformat()})
            last_heartbeat = time.monotonic()


@router.get('/events')
async def events(request:Request,user=Depends(current_user),credentials=Depends(bearer)):
    return StreamingResponse(event_stream(request,user,credentials),media_type='text/event-stream',
        headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
