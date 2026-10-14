"""CRUD, карточки и переходы статусов; общие операции — в api_shared."""
from datetime import datetime
from fastapi import APIRouter,Depends,HTTPException,Request,Query
from sqlalchemy import select,func
from .auth import current_user,ok
from .db import table,transaction
from .resources import RESOURCES,resource,scope,visible,public,descriptors,clean_values,check_references
from .security import hash_password
from .domain import validate_work_order
from .api_shared import mutation,filters,enrich

router=APIRouter(prefix='/api',tags=['Данные'])

@router.get('/meta')
def meta(user=Depends(current_user)):
    return ok(descriptors(user))

@router.get('/lookups')
def lookups(user=Depends(current_user)):
    result={}
    with transaction(user['Id']) as conn:
        for key,(name,_,_) in RESOURCES.items():
            t=table(name)
            if key=='users':
                query=select(t.c.Id,t.c.LastName,t.c.FirstName).where(t.c.IsActive==True)
                if user['Role'] in ('master','member'): query=query.where(t.c.Id==user['Id'])
                rows=conn.execute(query).mappings()
                result[key]=[{'id':r['Id'],'label':r['LastName']+' '+r['FirstName']} for r in rows]
                continue
            columns=[t.c.Id]
            namecol='Name' if 'Name' in t.c else 'Number' if 'Number' in t.c else 'Id'
            columns.append(t.c[namecol].label('Label'))
            if name=='Equipment': columns.append(t.c.WorkshopId)
            clauses=scope(t,user)
            if 'IsDeleted' in t.c: clauses.append(t.c.IsDeleted==False)
            rows=conn.execute(select(*columns).where(*clauses).order_by(t.c.Id).limit(10000)).mappings()
            result[key]=[{'id':r['Id'],'label':str(r['Label']),**({'workshop_id':r['WorkshopId']} if name=='Equipment' else {})} for r in rows]
        result['roles']=[{'id':r.Id,'label':r.Name} for r in conn.execute(select(table('Roles')))]
        users,roles,orders=table('Users'),table('Roles'),table('WorkOrders')
        masters=select(users.c.Id,users.c.LastName,users.c.FirstName,users.c.WorkshopId).join(roles,roles.c.Id==users.c.RoleId).where(users.c.IsActive==True,roles.c.Code=='master')
        if user['Role']=='master': masters=masters.where(users.c.Id==user['Id'])
        elif user['Role']=='member': masters=masters.where(users.c.Id.in_(select(orders.c.MasterId).where(*scope(orders,user))))
        result['masters']=[{'id':r.Id,'label':r.LastName+' '+r.FirstName,'workshop_id':r.WorkshopId} for r in conn.execute(masters)]
    return ok(result)

@router.get('/{key}/{ident}/history')
def history(key:str,ident:int,user=Depends(current_user)):
    if key not in ('equipment','work-orders'): raise HTTPException(404,'История недоступна.')
    t=resource(key,user)
    with transaction(user['Id']) as conn:
        visible(conn,t,ident,user)
        hist=table('EquipmentStatusHistory' if key=='equipment' else 'WorkOrderStatusHistory')
        fk='EquipmentId' if key=='equipment' else 'WorkOrderId'
        rows=conn.execute(select(hist).where(hist.c[fk]==ident).order_by(hist.c.ChangedAt.desc(),hist.c.Id.desc())).mappings()
        return ok([public(r) for r in rows])

@router.post('/work-orders/{ident}/transition')
def transition(ident:int,payload:dict,request:Request,user=Depends(current_user)):
    if user['Role'] not in ('admin','engineer','master','member'): raise HTTPException(403,'Нет права менять статусы.')
    def perform(conn):
        t=table('WorkOrders'); old=visible(conn,t,ident,user)
        status=payload.get('status')
        if user['Role']=='member' and status not in ('в работе','ожидает материалов','выполнена'): raise HTTPException(403,'Бригада может начать, приостановить или завершить работу.')
        values={'Status':status}
        for source,dest in [('team_id','TeamId'),('actual_start','ActualStart'),('actual_end','ActualEnd'),('completion_report','CompletionReport')]:
            if payload.get(source) is not None: values[dest]=payload[source]
        if status=='в работе' and not old['ActualStart'] and 'ActualStart' not in values:
            # SQL datetime2(0) can round CreatedAt up to the next whole second.
            values['ActualStart']=max(datetime.utcnow().replace(microsecond=0),old['CreatedAt'])
        if status=='выполнена' and 'ActualEnd' not in values: values['ActualEnd']=datetime.utcnow().replace(microsecond=0)
        values=clean_values(t,values)
        check_references(conn,t,values,user,old)
        conn.execute(t.update().where(t.c.Id==ident).values(**values))
        return ok(public(visible(conn,t,ident,user)),'Статус изменён.')
    return mutation(request,user,payload,perform)

@router.get('/work-orders/{ident}/materials')
def order_materials(ident:int,user=Depends(current_user)):
    with transaction(user['Id']) as conn:
        visible(conn,table('WorkOrders'),ident,user)
        t,m=table('WorkOrderMaterials'),table('Materials')
        rows=conn.execute(select(t,m.c.Name.label('MaterialName'),m.c.Unit).join(m,t.c.MaterialId==m.c.Id).where(t.c.WorkOrderId==ident)).mappings()
        return ok([public(r) for r in rows])

def material_mutation(ident,material_id,payload,request,user,action):
    if user['Role'] not in ('admin','master','member'): raise HTTPException(403,'Списание разрешено мастеру и бригаде.')
    def perform(conn):
        order=visible(conn,table('WorkOrders'),ident,user)
        if order['Status'] in ('закрыта','отменена'): raise HTTPException(409,'Материалы закрытой/отменённой заявки менять нельзя.')
        t=table('WorkOrderMaterials')
        if action=='add':
            values=clean_values(t,{'WorkOrderId':ident,**payload},creating=True)
            # Historical price is always selected on server, never trusted from client.
            m=conn.execute(select(table('Materials')).where(table('Materials').c.Id==values['MaterialId'])).mappings().first()
            if not m: raise HTTPException(404,'Материал не найден.')
            values['UnitPrice']=m['UnitPrice']; values['WorkOrderId']=ident
            conn.execute(t.insert().values(**values))
        else:
            where=(t.c.WorkOrderId==ident,t.c.MaterialId==material_id)
            if not conn.execute(select(t).where(*where)).first(): raise HTTPException(404,'Списание не найдено.')
            if action=='delete': conn.execute(t.delete().where(*where))
            else:
                if set(payload)-{'Quantity','Comment'}: raise HTTPException(400,'Можно изменить только количество и комментарий.')
                conn.execute(t.update().where(*where).values(**clean_values(t,payload)))
        return ok(message='Материалы обновлены.')
    return mutation(request,user,payload,perform)

@router.post('/work-orders/{ident}/materials',status_code=201)
def add_material(ident:int,payload:dict,request:Request,user=Depends(current_user)):
    return material_mutation(ident,None,payload,request,user,'add')
@router.put('/work-orders/{ident}/materials/{material_id}')
def edit_material(ident:int,material_id:int,payload:dict,request:Request,user=Depends(current_user)):
    return material_mutation(ident,material_id,payload,request,user,'edit')
@router.delete('/work-orders/{ident}/materials/{material_id}')
def remove_material(ident:int,material_id:int,request:Request,user=Depends(current_user)):
    return material_mutation(ident,material_id,{},request,user,'delete')

@router.get('/{key}')
def listing(key:str,user=Depends(current_user),search:str=Query('',max_length=150),status:str|None=None,
            workshop_id:int|None=None,workshop_ids:str|None=None,equipment_id:int|None=None,team_id:int|None=None,
            priority:str|None=None,order_type:str|None=Query(None,alias='type'),
            model:str|None=Query(None,max_length=150),location:str|None=Query(None,max_length=200),
            start:str|None=Query(None,alias='from'),end:str|None=Query(None,alias='to'),
            date_from:str|None=None,date_to:str|None=None,upcoming_days:int|None=Query(None,ge=1,le=366),overdue:bool=False,
            page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),sort_by:str='Id',sort_dir:str=Query('desc',pattern='^(asc|desc)$')):
    t=resource(key,user)
    if sort_by not in t.c or sort_by in ('PasswordHash','Version'): raise HTTPException(400,'Недопустимое поле сортировки.')
    with transaction(user['Id']) as conn:
        conditions=filters(t,user,search,status,workshop_id,workshop_ids_value=workshop_ids,
            equipment_id=equipment_id,team_id=team_id,priority=priority,order_type=order_type,
            start=start or date_from,end=end or date_to)
        for value,column in ((model,'Model'),(location,'Location')):
            if value and column in t.c: conditions.append(t.c[column].contains(value,autoescape=True))
        if t.name=='MaintenanceSchedule' and (upcoming_days or overdue):
            from datetime import timedelta
            now=datetime.utcnow()
            conditions.append(t.c.Status.not_in(['выполнено','отменено']))
            if overdue: conditions.append(t.c.PlannedAt<now)
            else: conditions.extend([t.c.PlannedAt>=now,t.c.PlannedAt<now+timedelta(days=upcoming_days)])
        total=conn.execute(select(func.count()).select_from(t).where(*conditions)).scalar_one()
        ordering=t.c[sort_by].asc() if sort_dir=='asc' else t.c[sort_by].desc()
        ordered=[ordering] if sort_by=='Id' else [ordering,t.c.Id]
        rows=[public(r) for r in conn.execute(select(t).where(*conditions).order_by(*ordered).offset((page-1)*page_size).limit(page_size)).mappings()]
        if t.name=='MaintenanceSchedule':
            now=datetime.utcnow().isoformat()
            for row in rows: row['IsOverdue']=row['PlannedAt']<now and row['Status'] not in ('выполнено','отменено')
        return ok({'items':enrich(conn,t.name,rows),'total':total,'page':page,'page_size':page_size})

@router.get('/{key}/{ident}')
def detail(key:str,ident:int,user=Depends(current_user)):
    with transaction(user['Id']) as conn:
        t=resource(key,user)
        result=public(visible(conn,t,ident,user))
        if key in ('equipment','work-orders'):
            history_table=table('EquipmentStatusHistory' if key=='equipment' else 'WorkOrderStatusHistory')
            field='EquipmentId' if key=='equipment' else 'WorkOrderId'
            result['history']=[public(row) for row in conn.execute(select(history_table)
                .where(history_table.c[field]==ident).order_by(history_table.c.ChangedAt,history_table.c.Id)).mappings()]
        if key=='equipment':
            for result_key,name in [('orders','WorkOrders'),('schedule','MaintenanceSchedule')]:
                child=table(name)
                result[result_key]=enrich(conn,name,[public(row) for row in conn.execute(select(child)
                    .where(child.c.EquipmentId==ident,*scope(child,user)).order_by(child.c.Id.desc())).mappings()])
        if key=='work-orders':
            child,material=table('WorkOrderMaterials'),table('Materials')
            result['materials']=[public(row) for row in conn.execute(select(child,material.c.Name.label('MaterialName'),material.c.Unit)
                .join(material,material.c.Id==child.c.MaterialId).where(child.c.WorkOrderId==ident)).mappings()]
        if key=='teams':
            users,orders=table('Users'),table('WorkOrders')
            # Public contact roster only: never expose credential fields.
            result['members']=[public(row) for row in conn.execute(select(users.c.Id,users.c.LastName,users.c.FirstName,
                users.c.Patronymic,users.c.Email,users.c.Phone,users.c.IsActive).where(users.c.TeamId==ident)).mappings()]
            active=[dict(row) for row in conn.execute(select(orders).where(orders.c.TeamId==ident,*scope(orders,user),
                orders.c.Status.not_in(['выполнена','закрыта','отменена']))).mappings()]
            result['active_orders']=enrich(conn,'WorkOrders',[public(row) for row in active])
            result['workload']={'active':len(active),'planned_hours':round(sum((row['PlannedEnd']-row['PlannedStart']).total_seconds()/3600 for row in active),2)}
        return ok(result)

@router.post('/{key}',status_code=201)
def create(key:str,payload:dict,request:Request,user=Depends(current_user)):
    t=resource(key,user,write=True)
    def perform(conn):
        values=clean_values(t,payload,creating=True)
        if t.name=='Users':
            if not payload.get('Password'): raise HTTPException(400,'Пароль обязателен.')
            try: values['PasswordHash']=hash_password(payload['Password'])
            except ValueError as ex: raise HTTPException(400,str(ex))
        if t.name=='Equipment': values.update(CreatedBy=user['Id'],UpdatedBy=user['Id'])
        if t.name=='WorkOrders':
            errors=validate_work_order(values)
            if errors: raise HTTPException(400,' '.join(errors))
            if values.get('Status','создана')!='создана': raise HTTPException(400,'Новая заявка начинается со статуса «создана».')
        check_references(conn,t,values,user)
        result=conn.execute(t.insert().values(**values))
        ident=result.inserted_primary_key[0]
        return ok(public(visible(conn,t,ident,user)),'Запись создана.')
    return mutation(request,user,payload,perform)

@router.put('/{key}/{ident}')
def edit(key:str,ident:int,payload:dict,request:Request,user=Depends(current_user)):
    t=resource(key,user,write=True)
    def perform(conn):
        old=visible(conn,t,ident,user)
        if payload.get('_version') and isinstance(old.get('Version'),bytes) and old['Version'].hex()!=payload['_version']: raise HTTPException(409,'Запись уже изменена другим пользователем. Обновите список.')
        values=clean_values(t,payload)
        if t.name=='Materials' and 'Stock' in values and values['Stock']<old['Stock']:
            raise HTTPException(400,'Уменьшать остаток можно только списанием материала в заявке.')
        if t.name=='WorkOrders':
            if 'Status' in values and values['Status']!=old['Status']: raise HTTPException(400,'Меняйте статус кнопкой перехода, а не общей формой.')
            errors=validate_work_order({**old,**values})
            if errors: raise HTTPException(400,' '.join(errors))
        if t.name=='Users' and payload.get('Password'):
            try: values['PasswordHash']=hash_password(payload['Password'])
            except ValueError as ex: raise HTTPException(400,str(ex))
            conn.execute(table('RefreshTokens').update().where(table('RefreshTokens').c.UserId==ident).values(RevokedAt=datetime.utcnow()))
        if t.name=='Users' and ident==user['Id'] and (values.get('IsActive') is False or values.get('RoleId',old['RoleId'])!=old['RoleId']): raise HTTPException(400,'Нельзя отключить себя или изменить собственную роль.')
        if t.name=='Equipment': values.update(UpdatedBy=user['Id'],UpdatedAt=datetime.utcnow())
        check_references(conn,t,values,user,old)
        where=[t.c.Id==ident]
        if payload.get('_version') and 'Version' in t.c: where.append(t.c.Version==old['Version'])
        if not values: raise HTTPException(400,'Нет изменяемых полей.')
        result=conn.execute(t.update().where(*where).values(**values))
        if result.rowcount==0: raise HTTPException(409,'Запись изменилась. Обновите данные.')
        return ok(public(visible(conn,t,ident,user)),'Запись обновлена.')
    return mutation(request,user,payload,perform)

@router.delete('/{key}/{ident}')
def remove(key:str,ident:int,request:Request,user=Depends(current_user)):
    t=resource(key,user,write=True)
    def perform(conn):
        old=visible(conn,t,ident,user)
        if t.name=='Users':
            if ident==user['Id']: raise HTTPException(400,'Нельзя отключить собственную учётную запись.')
            conn.execute(t.update().where(t.c.Id==ident).values(IsActive=False))
            conn.execute(table('RefreshTokens').update().where(table('RefreshTokens').c.UserId==ident).values(RevokedAt=datetime.utcnow()))
        elif t.name=='Equipment':
            orders,sched=table('WorkOrders'),table('MaintenanceSchedule')
            active=conn.execute(select(func.count()).select_from(orders).where(orders.c.EquipmentId==ident,orders.c.Status.not_in(['закрыта','отменена']))).scalar()
            active+=conn.execute(select(func.count()).select_from(sched).where(sched.c.EquipmentId==ident,sched.c.Status!='отменено')).scalar()
            if active: raise HTTPException(409,'Сначала завершите заявки и график оборудования.')
            conn.execute(t.update().where(t.c.Id==ident).values(IsDeleted=True,UpdatedBy=user['Id']))
        else:
            if t.name=='WorkOrders' and old['Status']!='создана': raise HTTPException(409,'Удалять можно только ещё не назначенную заявку в статусе «создана».')
            conn.execute(t.delete().where(t.c.Id==ident))
        return ok(message='Запись удалена или деактивирована с сохранением истории.')
    return mutation(request,user,{},perform)
