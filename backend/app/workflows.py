"""Плановое ТО и атомарное завершение заявки со списанием материалов."""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, text
from .auth import current_user, ok
from .db import table, transaction
from .resources import scope, public, visible, clean_values, check_references
from .api_shared import mutation, enrich, filters
from .querying import utc_value

# Префикс /api добавляется родительским роутером advanced.
router = APIRouter(tags=['Планирование и выполнение'])


@router.get('/schedule/upcoming')
def upcoming(user=Depends(current_user), days:int=Query(7,ge=1,le=366), workshop_id:int|None=None,
             equipment_id:int|None=None):
    return schedule_window(user, False, days, workshop_id, equipment_id)


@router.get('/schedule/overdue')
def overdue(user=Depends(current_user), workshop_id:int|None=None, equipment_id:int|None=None):
    return schedule_window(user, True, 7, workshop_id, equipment_id)


def schedule_window(user, is_overdue, days, workshop_id, equipment_id):
    t = table('MaintenanceSchedule')
    now = datetime.utcnow()
    conditions = filters(t,user,workshop_id=workshop_id,equipment_id=equipment_id)
    conditions.append(t.c.Status.not_in(['выполнено','отменено']))
    if is_overdue: conditions.append(t.c.PlannedAt < now)
    else: conditions.extend([t.c.PlannedAt >= now,t.c.PlannedAt < now + timedelta(days=days)])
    with transaction(user['Id']) as conn:
        rows = [public(row) for row in conn.execute(select(t).where(*conditions).order_by(t.c.PlannedAt,t.c.Id)).mappings()]
        for row in rows: row['IsOverdue'] = is_overdue
        return ok({'items':enrich(conn,t.name,rows),'total':len(rows)})


@router.post('/schedule/{ident}/create-order',status_code=201)
def create_schedule_order(ident:int,payload:dict,request:Request,user=Depends(current_user)):
    if user['Role'] not in ('admin','engineer','master'):
        raise HTTPException(403,'Создавать плановые заявки может мастер или инженер.')
    if set(payload)-{'master_id','planned_hours','planned_start','priority','team_id'}:
        raise HTTPException(400,'Неизвестные поля плановой заявки.')
    try:
        if isinstance(payload['master_id'],bool) or isinstance(payload['master_id'],float) and not payload['master_id'].is_integer(): raise ValueError()
        master_id = int(payload['master_id'])
        if master_id <= 0 or master_id>2147483647: raise ValueError()
    except (KeyError,ValueError,TypeError): raise HTTPException(400,'master_id обязателен.')

    def perform(conn):
        schedule, orders = table('MaintenanceSchedule'), table('WorkOrders')
        # Independent of the client idempotency key: one schedule can create only one order.
        result = conn.execute(text("DECLARE @r int; EXEC @r=sys.sp_getapplock @Resource=:r,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000; SELECT @r"),
                              {'r':f'schedule-order:{ident}'}).scalar()
        if result < 0: raise HTTPException(409,'Создание заявки уже выполняется. Повторите запрос.')
        row = visible(conn,schedule,ident,user)
        existing = conn.execute(select(orders).where(orders.c.ScheduleId==ident,*scope(orders,user))).mappings().first()
        if existing:
            return ok({**public(existing),'ScheduleOrderReused':True},'Для записи графика уже существует заявка.')
        if row['Status'] in ('выполнено','отменено'):
            raise HTTPException(409,'Завершённая или отменённая запись графика недоступна для создания заявки.')
        equipment = visible(conn,table('Equipment'),row['EquipmentId'],user)
        users, roles = table('Users'),table('Roles')
        master = conn.execute(select(users).join(roles,roles.c.Id==users.c.RoleId)
            .where(users.c.Id==master_id,users.c.IsActive==True,roles.c.Code=='master')).mappings().first()
        if not master or master['WorkshopId'] != equipment['WorkshopId']:
            raise HTTPException(400,'Выберите активного мастера цеха этого оборудования.')
        if user['Role']=='master' and master_id!=user['Id']:
            raise HTTPException(403,'Мастер создаёт заявку от своего имени.')
        maintenance = conn.execute(select(table('MaintenanceTypes')).where(table('MaintenanceTypes').c.Id==row['MaintenanceTypeId'])).mappings().one()
        if not maintenance['IsActive']: raise HTTPException(409,'Вид ТО отключён.')
        duration = maintenance['PlannedHours']
        norms = table('MaintenanceNorms')
        norm = conn.execute(select(norms.c.MinimumHours).where(norms.c.EquipmentTypeId==equipment['EquipmentTypeId'],
                    norms.c.MaintenanceTypeId==maintenance['Id'])).scalar()
        if norm is not None: duration = norm
        try:
            duration = Decimal(str(payload.get('planned_hours',duration)))
            if not duration.is_finite() or duration<=0 or duration>100000: raise ValueError()
        except (InvalidOperation,ValueError,TypeError): raise HTTPException(400,'planned_hours должно быть положительным числом.')
        start = utc_value(payload['planned_start'],'planned_start') if payload.get('planned_start') else row['PlannedAt']
        created = datetime.utcnow().replace(microsecond=0)
        if start < created:
            raise HTTPException(400,'Плановая дата уже прошла. Укажите planned_start не раньше текущего времени.')
        priority = payload.get('priority','средний')
        if priority not in ('низкий','средний','высокий','критический'):
            raise HTTPException(400,'Недопустимый приоритет.')
        team_id = payload.get('team_id',row['TeamId'])
        if team_id is not None:
            try:
                if isinstance(team_id,bool) or isinstance(team_id,float) and not team_id.is_integer(): raise ValueError()
                team_id=int(team_id)
                if team_id<=0 or team_id>2147483647: raise ValueError()
            except (ValueError,TypeError): raise HTTPException(400,'Некорректный team_id.')
            team = visible(conn,table('Teams'),team_id,user)
            if not team['IsActive']: raise HTTPException(400,'Выбранная бригада неактивна.')
        try: finish=start+timedelta(seconds=float(duration*3600))
        except OverflowError: raise HTTPException(400,'Окончание работ выходит за допустимый диапазон дат.')
        values = dict(EquipmentId=row['EquipmentId'],MaintenanceTypeId=row['MaintenanceTypeId'],ScheduleId=ident,
            MasterId=master_id,TeamId=team_id,Type='плановая',Priority=priority,Status='создана',
            Description=f"Плановое обслуживание: {maintenance['Name']}",CreatedAt=created,
            PlannedStart=start,PlannedEnd=finish)
        inserted = conn.execute(orders.insert().values(**values))
        order_id = inserted.inserted_primary_key[0]
        if team_id is not None:
            conn.execute(orders.update().where(orders.c.Id==order_id).values(Status='назначена'))
        result = public(visible(conn,orders,order_id,user))
        return ok({**result,'ScheduleOrderReused':False},'Плановая заявка создана.')
    return mutation(request,user,payload,perform)


@router.post('/work-orders/{ident}/complete')
def complete_order(ident:int,payload:dict,request:Request,user=Depends(current_user)):
    """Report, optional material consumption and completion commit in one transaction."""
    if user['Role'] not in ('admin','engineer','master','member'):
        raise HTTPException(403,'Нет права завершать заявку.')
    if set(payload)-{'completion_report','actual_end','materials'}:
        raise HTTPException(400,'Неизвестные поля завершения заявки.')
    materials=payload.get('materials',[])
    if not isinstance(materials,list) or len(materials)>100:
        raise HTTPException(400,'materials: ожидается список не более 100 материалов.')
    if materials and user['Role']=='engineer':
        raise HTTPException(403,'Инженер не имеет права списывать материалы.')
    report=payload.get('completion_report')
    if not isinstance(report,str) or not report.strip():
        raise HTTPException(400,'Отчёт о выполненных работах обязателен.')

    def perform(conn):
        orders,lines=table('WorkOrders'),table('WorkOrderMaterials')
        # Serialize finish/material changes for this order even without an idempotency key.
        conn.execute(select(orders.c.Id).where(orders.c.Id==ident,*scope(orders,user)).with_hint(orders,'WITH (UPDLOCK,HOLDLOCK)','mssql')).first()
        old=visible(conn,orders,ident,user)
        if old['Status']!='в работе':
            raise HTTPException(409,'Завершить можно заявку в работе. Возобновите приостановленную заявку.')
        end=utc_value(payload['actual_end'],'actual_end') if payload.get('actual_end') else datetime.utcnow().replace(microsecond=0)
        if old['ActualStart'] is None or end<=old['ActualStart']:
            raise HTTPException(400,'Фактическое окончание должно быть позже начала. Укажите время или повторите через секунду.')
        if end>datetime.utcnow()+timedelta(seconds=1):
            raise HTTPException(400,'Фактическое окончание не может быть в будущем.')
        seen=set()
        for item in materials:
            if not isinstance(item,dict) or set(item)-{'MaterialId','Quantity','Comment'}:
                raise HTTPException(400,'Материал: укажите MaterialId, Quantity и необязательный Comment.')
            values=clean_values(lines,{'WorkOrderId':ident,**item},creating=True)
            material_id=values['MaterialId']
            if material_id in seen: raise HTTPException(400,'Материал повторяется в списке.')
            seen.add(material_id)
            material=visible(conn,table('Materials'),material_id,user)
            values['UnitPrice']=material['UnitPrice']
            conn.execute(lines.insert().values(**values))
        values=clean_values(orders,{'Status':'выполнена','ActualEnd':end,'CompletionReport':report})
        check_references(conn,orders,values,user,old)
        conn.execute(orders.update().where(orders.c.Id==ident).values(**values))
        return ok(public(visible(conn,orders,ident,user)),'Заявка завершена, материалы и отчёт сохранены атомарно.')
    return mutation(request,user,payload,perform)
