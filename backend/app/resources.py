from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import select, or_, and_, String, Integer, Numeric, Boolean, DateTime, Date, LargeBinary
from fastapi import HTTPException
from .db import table

RESOURCES = {
 'equipment':('Equipment','Оборудование',{'admin','engineer','master'}),
 'work-orders':('WorkOrders','Заявки',{'admin','engineer','master'}),
 'schedule':('MaintenanceSchedule','График ТО',{'admin','engineer','master'}),
 'materials':('Materials','Материалы',{'admin','engineer','master'}),
 'teams':('Teams','Бригады',{'admin','engineer','master'}),
 'maintenance-types':('MaintenanceTypes','Виды ТО',{'admin','engineer'}),
 'workshops':('Workshops','Цеха',{'admin','engineer'}),
 'suppliers':('Suppliers','Поставщики',{'admin','engineer'}),
 'equipment-types':('EquipmentTypes','Типы оборудования',{'admin','engineer'}),
 'users':('Users','Пользователи',{'admin'}),
}
ENUMS={
 ('Equipment','Status'):['в работе','в ремонте','в простое','выведено из эксплуатации'],
 ('WorkOrders','Status'):['создана','назначена','в работе','ожидает материалов','выполнена','закрыта','отменена'],
 ('WorkOrders','Type'):['плановая','аварийная','текущая'],
 ('WorkOrders','Priority'):['низкий','средний','высокий','критический'],
 ('MaintenanceSchedule','Status'):['запланировано','назначено','выполняется','выполнено','отменено','просрочено'],
 ('MaintenanceTypes','IntervalKind'):['days','hours','condition'],
}
LOOKUPS={'WorkshopId':'workshops','RoleId':'roles','TeamId':'teams','MasterId':'masters','EquipmentId':'equipment','MaintenanceTypeId':'maintenance-types','ScheduleId':'schedule','SupplierId':'suppliers','EquipmentTypeId':'equipment-types'}
READ_ONLY={'Id','Version','Number','SequenceNumber','RegisteredAt','CreatedAt','UpdatedAt','CreatedBy','UpdatedBy','IsDeleted'}
LABELS={'Id':'ID','Code':'Код','Name':'Наименование','Email':'Email','Phone':'Телефон','LastName':'Фамилия','FirstName':'Имя','Patronymic':'Отчество','Password':'Пароль','RoleId':'Роль','WorkshopId':'Цех','TeamId':'Бригада','IsActive':'Активен','InventoryNumber':'Инвентарный номер','Model':'Модель','SerialNumber':'Заводской номер','CommissionedOn':'Ввод в эксплуатацию','StartedOn':'Ввод в работу','RetiredOn':'Дата списания','Status':'Статус','Manufacturer':'Производитель','WarrantyUntil':'Гарантия до','PassportUrl':'Ссылка на паспорт','EquipmentId':'Оборудование','EquipmentTypeId':'Тип оборудования','MaintenanceTypeId':'Вид ТО','IntervalKind':'Единица периодичности','IntervalDays':'Период, дней','IntervalHours':'Период, моточасов','PlannedHours':'Длительность, ч','RequiresStop':'Требуется остановка','Description':'Описание','PlannedAt':'Дата ТО','CancellationReason':'Причина отмены','MasterId':'Ответственный мастер','ScheduleId':'Запись графика','Type':'Тип заявки','Priority':'Приоритет','FailureReason':'Причина отказа','PlannedStart':'Плановое начало','PlannedEnd':'Плановое окончание','ActualStart':'Фактическое начало','ActualEnd':'Фактическое окончание','CompletionReport':'Отчёт о работах','Number':'Номер','CreatedAt':'Создано','UpdatedAt':'Изменено','Specialization':'Специализация','Unit':'Единица измерения','Stock':'Остаток','MinimumStock':'Минимальный остаток','Location':'Место хранения','UnitPrice':'Цена','SupplierId':'Поставщик','Quantity':'Количество','Version':'Версия'}

def resource(key, user, write=False):
    if key not in RESOURCES: raise HTTPException(404,'Раздел не найден.')
    name,label,writers=RESOURCES[key]
    if key=='users' and user['Role']!='admin': raise HTTPException(403,'Раздел доступен администратору.')
    if write and user['Role'] not in writers: raise HTTPException(403,'Недостаточно прав для изменения.')
    return table(name)

def scope(t,user):
    role=user['Role']
    if role not in ('master','member'): return []
    equipment=table('Equipment'); orders=table('WorkOrders')
    if role=='master':
        ids=select(equipment.c.Id).where(equipment.c.WorkshopId==user['WorkshopId'])
        if t.name=='Equipment': return [t.c.WorkshopId==user['WorkshopId']]
        if t.name in ('WorkOrders','MaintenanceSchedule'): return [t.c.EquipmentId.in_(ids)]
        if t.name=='Workshops': return [t.c.Id==user['WorkshopId']]
        if t.name=='Teams': return [or_(t.c.WorkshopId==user['WorkshopId'],t.c.WorkshopId.is_(None))]
    if role=='member':
        if t.name=='WorkOrders': return [t.c.TeamId==user['TeamId']]
        if t.name=='Equipment': return [t.c.Id.in_(select(orders.c.EquipmentId).where(orders.c.TeamId==user['TeamId']))]
        if t.name=='MaintenanceSchedule': return [t.c.TeamId==user['TeamId']]
        if t.name=='Teams': return [t.c.Id==user['TeamId']]
        if t.name=='Workshops': return [t.c.Id==user['WorkshopId']]
    return []

def visible(conn,t,ident,user):
    row=conn.execute(select(t).where(t.c.Id==ident,*scope(t,user))).mappings().first()
    if not row: raise HTTPException(404,'Запись не найдена или недоступна.')
    return dict(row)

def public(row):
    out={}
    for key,value in dict(row).items():
        if key in ('PasswordHash','TokenHash'): continue
        if isinstance(value, bytes): value=value.hex()
        elif isinstance(value, Decimal): value=float(value)
        elif isinstance(value,(datetime,date)): value=value.isoformat()
        out[key]=value
    if 'Number' in out and out.get('SequenceNumber') is not None and out.get('CreatedAt'):
        out['DisplayNumber']=f"Z-{str(out['CreatedAt'])[:4]}-{int(out['SequenceNumber']):04d}"
    return out

def descriptors(user):
    result=[]
    for key,(name,label,writers) in RESOURCES.items():
        if key=='users' and user['Role']!='admin': continue
        t=table(name); fields=[]
        for c in t.c:
            if c.name=='PasswordHash' or c.name in ('CreatedBy','UpdatedBy','IsDeleted','SequenceNumber'): continue
            kind='text'
            if isinstance(c.type,Boolean): kind='bool'
            elif isinstance(c.type,(Integer,Numeric)): kind='number'
            elif isinstance(c.type,DateTime): kind='datetime'
            elif isinstance(c.type,Date): kind='date'
            elif getattr(c.type,'length',0) and c.type.length>500: kind='textarea'
            options=ENUMS.get((name,c.name)); lookup=LOOKUPS.get(c.name)
            if options or lookup: kind='select'
            fields.append({'name':c.name,'label':LABELS.get(c.name,c.name),'type':kind,'required':not c.nullable and c.server_default is None and c.name not in READ_ONLY,'readOnly':c.name in READ_ONLY,'options':options,'lookup':lookup})
        if name=='Users': fields.append({'name':'Password','label':'Пароль (при изменении можно оставить пустым)','type':'password','required':False,'readOnly':False})
        result.append({'key':key,'label':label,'fields':fields,'canWrite':user['Role'] in writers,'canDelete':user['Role'] in writers and key not in ('workshops','maintenance-types','equipment-types')})
    return {'resources':result,'statuses':{'equipment':ENUMS[('Equipment','Status')],'work-orders':ENUMS[('WorkOrders','Status')],'schedule':ENUMS[('MaintenanceSchedule','Status')]}}

def clean_values(t,data,creating=False):
    values={}
    unknown=set(data)-set(t.c.keys())-{'Password','_version'}
    if unknown: raise HTTPException(400,'Неизвестные поля: '+', '.join(sorted(unknown)))
    for name,value in data.items():
        if name in READ_ONLY or name in ('PasswordHash','Password','_version'): continue
        c=t.c[name]
        if value=='' and (c.nullable or not isinstance(c.type,String)): value=None
        try:
            if value is not None:
                if isinstance(c.type,DateTime):
                    value=datetime.fromisoformat(str(value).replace('Z','+00:00')) if not isinstance(value,datetime) else value
                    if value.tzinfo: value=value.astimezone(timezone.utc).replace(tzinfo=None)
                elif isinstance(c.type,Date): value=date.fromisoformat(str(value)[:10]) if not isinstance(value,date) else value
                elif isinstance(c.type,Boolean):
                    if value not in (True,False,0,1): raise ValueError('boolean required')
                    value=bool(value)
                elif isinstance(c.type,Integer):
                    if isinstance(value,float) and not value.is_integer(): raise ValueError('integer required')
                    value=int(value)
                elif isinstance(c.type,Numeric):
                    value=Decimal(str(value))
                    if not value.is_finite(): raise ValueError('finite required')
                elif isinstance(c.type,String):
                    value=str(value).strip()
                    if not c.nullable and not value: raise ValueError('empty')
                    if c.type.length and len(value)>c.type.length: raise ValueError('too long')
            if value is None and not c.nullable: raise ValueError('required')
        except (ValueError,TypeError,ArithmeticError): raise HTTPException(400,'Некорректное поле: '+LABELS.get(name,name))
        values[name]=value
    if creating:
        missing=[c.name for c in t.c if not c.nullable and c.server_default is None and c.identity is None and c.computed is None and c.name not in values and c.name not in READ_ONLY and c.name!='PasswordHash']
        if missing: raise HTTPException(400,'Заполните поля: '+', '.join(LABELS.get(n,n) for n in missing))
    return values

def check_references(conn,t,values,user,existing=None):
    combined={**(existing or {}),**values}
    for field,target in [('EquipmentId','Equipment'),('TeamId','Teams'),('WorkshopId','Workshops'),('ScheduleId','MaintenanceSchedule')]:
        if field in combined and combined[field] is not None:
            visible(conn,table(target),combined[field],user)
    if t.name=='WorkOrders' and user['Role']=='master' and (existing is None or values.get('MasterId',existing.get('MasterId'))!=existing.get('MasterId')) and combined.get('MasterId')!=user['Id']:
        raise HTTPException(403,'Мастер создаёт и изменяет заявки от своего имени.')
    if t.name=='WorkOrders' and (existing is None or 'MasterId' in values or 'EquipmentId' in values):
        users,roles=table('Users'),table('Roles')
        master=conn.execute(select(users.c.WorkshopId).join(roles,roles.c.Id==users.c.RoleId)
            .where(users.c.Id==combined.get('MasterId'),users.c.IsActive==True,roles.c.Code=='master')).first()
        equipment=conn.execute(select(table('Equipment').c.WorkshopId).where(table('Equipment').c.Id==combined.get('EquipmentId'))).first()
        if not master or not equipment or master.WorkshopId!=equipment.WorkshopId:
            raise HTTPException(400,'Ответственным должен быть активный мастер цеха оборудования.')
