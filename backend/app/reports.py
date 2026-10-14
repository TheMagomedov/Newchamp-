"""HTTP отчёты, предварительный просмотр, выгрузка и атомарный импорт."""
import csv
import io
import secrets
import threading
import time
import zipfile
from datetime import datetime
from urllib.parse import quote
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from fastapi.responses import Response
from sqlalchemy import select,text
from openpyxl import load_workbook
from .auth import current_user,ok
from .db import table,transaction
from .resources import public,resource,clean_values,check_references,LABELS
from .api_shared import filters,enrich,mutation
from .analytics import summary
from .querying import bounds
from .report_layout import REPORT_COLUMNS,REPORT_LABELS,REPORT_TITLES
from .report_render import safe_cell,render_export

router=APIRouter(prefix='/api',tags=['Аналитика и отчёты'])
downloads={}
download_lock=threading.Lock()

def period(start=None,end=None):
    return bounds(start,end)

def analytics_options(user=Depends(current_user),start:str|None=Query(None,alias='from'),
                      end:str|None=Query(None,alias='to'),workshop_id:int|None=None,
                      workshop_ids:str|None=None,order_type:str|None=Query(None,alias='type'),
                      priority:str|None=None,equipment_id:int|None=None):
    return dict(user=user,start=start,end=end,workshop_id=workshop_id,workshop_ids=workshop_ids,
                order_type=order_type,priority=priority,equipment_id=equipment_id)

@router.get('/dashboard')
@router.get('/analytics')
@router.get('/analytics/dashboard')
@router.get('/analytics/dashboard-summary')
def dashboard(options=Depends(analytics_options)):
    return ok(summary(**options))

@router.get('/reports/summary')
def report_summary(options=Depends(analytics_options)):
    data=summary(**options)
    # Retain the legacy SQL procedure result where its whole-workshop scope applies.
    data['sql_report']=None
    user=options['user'];shop=options['workshop_id']
    extra_filters=any(options.get(key) for key in ('workshop_ids','order_type','priority','equipment_id'))
    if shop and not extra_filters and user['Role']!='member' and (user['Role']!='master' or user['WorkshopId']==shop):
        begin,finish=period(options['start'],options['end'])
        with transaction(user['Id']) as conn:
            row=conn.execute(text('EXEC dbo.GenerateWorkshopReport @WorkshopId=:shop,@StartAt=:start,@EndAt=:end'),
                {'shop':shop,'start':begin,'end':finish}).mappings().first()
            data['sql_report']=public(row) if row else None
    return ok(data)

@router.get('/analytics/downtime-dynamics')
def downtime_dynamics(options=Depends(analytics_options)):
    data=summary(**options)
    return ok({'items':data['downtime_daily'],'top_equipment':data['top_downtime'],'period':data['period']})

@router.get('/analytics/team-efficiency')
def team_efficiency(options=Depends(analytics_options)):
    return ok({'items':summary(**options)['team_rankings']})

def report_data(user,payload):
    kind=payload.get('type','equipment')
    if kind not in REPORT_TITLES: raise HTTPException(400,'Неизвестный тип отчёта.')
    options=dict(start=payload.get('from'),end=payload.get('to'),workshop_id=payload.get('workshop_id'),
                 workshop_ids=payload.get('workshop_ids'),order_type=payload.get('order_type'),
                 priority=payload.get('priority'),equipment_id=payload.get('equipment_id'))
    if kind in ('equipment','work-orders','materials'):
        t=resource(kind,user)
        conditions=filters(t,user,workshop_id=options['workshop_id'],workshop_ids_value=options['workshop_ids'],
                           equipment_id=options['equipment_id'],order_type=options['order_type'],priority=options['priority'],
                           start=options['start'] if kind=='work-orders' else None,end=options['end'] if kind=='work-orders' else None)
        with transaction(user['Id']) as conn:
            rows=enrich(conn,t.name,[public(row) for row in conn.execute(select(t).where(*conditions).order_by(t.c.Id)).mappings()])
        return {'type':kind,'title':REPORT_TITLES[kind],'columns':[{'key':key,'label':REPORT_LABELS.get(key,LABELS.get(key,key))} for key in REPORT_COLUMNS[kind]],
                'rows':rows,'summary':{'rows':len(rows)}}
    data=summary(user,**options)
    key={'downtime':'downtime_all','schedule':'schedule','team-efficiency':'team_rankings','material-usage':'materials_all','orders':'orders_daily'}
    if kind=='analytics':
        block=payload.get('block','all')
        block_types={'orders':'orders','downtime':'downtime','materials':'material-usage','schedule':'schedule','teams':'team-efficiency'}
        if block!='all':
            if block not in block_types: raise HTTPException(400,'Неизвестный блок аналитического отчёта.')
            return report_data(user,{**payload,'type':block_types[block]})
        metric_labels={'equipment':'Оборудование','repair_equipment':'В ремонте','open_orders':'Открытые заявки',
            'overdue':'Просроченные заявки','low_stock':'Материалы ниже минимума','downtime_hours':'Простой, ч',
            'today_orders':'Заявки за сегодня','avg_completion_hours':'Среднее время выполнения, ч',
            'completed_orders':'Выполнено за период','material_cost':'Стоимость материалов за период'}
        rows=[{'section':'Показатели','label':metric_labels[name],'value':value,'unit':'','detail':''} for name,value in data['metrics'].items()]
        for row in data['orders_daily']:
            rows.append({'section':'Заявки','label':row['date'],'value':row['created'],'unit':'создано','detail':f"Выполнено: {row['completed']}"})
        for row in data['downtime_daily']:
            rows.append({'section':'Простои','label':row['date'],'value':row['hours'],'unit':'ч','detail':''})
        for row in data['materials_all']:
            rows.append({'section':'Материалы','label':row['label'],'value':row['cost'],'unit':'стоимость','detail':f"{row['quantity']} {row['unit']}"})
        for row in data['schedule']['by_workshop']:
            rows.append({'section':'График ТО','label':row['label'],'value':row['completed'],'unit':'выполнено','detail':f"План: {row['planned']}; просрочено: {row['overdue']}"})
        for row in data['team_rankings']:
            average='нет завершённых заявок' if row['avg_completion_hours'] is None else str(row['avg_completion_hours'])+' ч'
            rows.append({'section':'Бригады','label':row['label'],'value':row['completed'],'unit':'выполнено','detail':f"Активных: {row['active']}; среднее время: {average}"})
    else:
        rows=data[key[kind]]['by_workshop'] if kind=='schedule' else data[key[kind]]
    chart_specs={
        'downtime':('Простой оборудования','downtime_all','label','hours','ч'),
        'material-usage':('Стоимость использованных материалов','materials_all','label','cost','руб.'),
        'team-efficiency':('Выполненные заявки по бригадам','team_rankings','label','completed','заявок'),
        'orders':('Созданные заявки за последние 30 дней периода','orders_daily','date','created','заявок')}
    charts=[]
    for chart_kind in (list(chart_specs) if kind=='analytics' else [kind]):
        if chart_kind in chart_specs:
            title,source,label,value,unit=chart_specs[chart_kind]
            items=[{'label':row[label],'value':row[value]} for row in data[source]]
            charts.append({'title':title,'unit':unit,'mode':'line' if chart_kind=='orders' else 'bar',
                           'items':items if chart_kind=='orders' else items[:12]})
    if kind in ('analytics','schedule'):
        charts.append({'title':'Выполненные ТО по цехам','unit':'ТО','items':[
            {'label':row['label'],'value':row['completed']} for row in data['schedule']['by_workshop']]})
    return {'type':kind,'title':REPORT_TITLES[kind],
            'columns':[{'key':name,'label':REPORT_LABELS.get(name,name)} for name in REPORT_COLUMNS[kind]],
            'rows':rows,'charts':charts,'summary':{'metrics':data['metrics'],'period':data['period'],'schedule':data['schedule']}}

@router.get('/reports/preview')
def preview(report_type:str=Query('equipment',alias='type'),block:str='all',user=Depends(current_user),
            start:str|None=Query(None,alias='from'),end:str|None=Query(None,alias='to'),
            workshop_id:int|None=None,workshop_ids:str|None=None,order_type:str|None=None,
            priority:str|None=None,equipment_id:int|None=None):
    return ok(report_data(user,{'type':report_type,'block':block,'from':start,'to':end,'workshop_id':workshop_id,
                               'workshop_ids':workshop_ids,'order_type':order_type,'priority':priority,'equipment_id':equipment_id}))

@router.post('/reports/export')
def export(payload:dict,user=Depends(current_user)):
    kind=payload.get('type','equipment');fmt=payload.get('format','xlsx')
    data=report_data(user,payload)
    kind=data['type']
    data['filters']={key:payload.get(key) for key in ('from','to','workshop_id','workshop_ids','equipment_id','order_type','priority','block')}
    content,mime=render_export(kind,fmt,data['rows'],data)
    token=secrets.token_urlsafe(32);filename=f'toir-{kind}-{datetime.utcnow():%Y%m%d}.{fmt}'
    with download_lock:
        for old in list(downloads):
            if downloads[old]['expires']<time.monotonic(): downloads.pop(old)
        downloads[token]={'owner':user['Id'],'content':content,'mime':mime,'filename':filename,'expires':time.monotonic()+15}
    return ok({'url':'/api/download/'+token,'expires_in':15,'filename':filename})

@router.get('/download/{token}')
@router.get('/files/{token}')
def download(token:str,user=Depends(current_user)):
    with download_lock: item=downloads.get(token)
    if not item or item['owner']!=user['Id']: raise HTTPException(404,'Файл не найден.')
    if item['expires']<time.monotonic():
        with download_lock: downloads.pop(token,None)
        raise HTTPException(410,'Ссылка истекла. Сформируйте отчёт заново.')
    return Response(item['content'],media_type=item['mime'],headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(item['filename']),'Cache-Control':'no-store'})

@router.post('/import/equipment')
async def import_equipment(request:Request,filename:str=Query('equipment.csv'),user=Depends(current_user)):
    if user['Role'] not in ('admin','engineer'): raise HTTPException(403,'Импорт доступен администратору и инженеру.')
    content=bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>2*1024*1024: raise HTTPException(400,'Максимальный размер файла 2 МБ.')
    try:
        if filename.lower().endswith('.xlsx'):
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(i.file_size for i in archive.infolist())>50*1024*1024: raise ValueError('Файл слишком большой после распаковки.')
            wb=load_workbook(io.BytesIO(content),read_only=True,data_only=True);raw=list(wb.active.values);wb.close()
            rows=[dict(zip(raw[0],row)) for row in raw[1:]]
        else:
            source=bytes(content).decode('utf-8-sig');dialect=csv.Sniffer().sniff(source[:2048],delimiters=',;\t')
            rows=list(csv.DictReader(io.StringIO(source),dialect=dialect))
        if not rows or len(rows)>10000: raise ValueError('Файл должен содержать 1–10000 записей.')
    except Exception as ex: raise HTTPException(400,'Не удалось прочитать CSV UTF-8 / XLSX: '+str(ex)[:120])
    def perform(conn):
        t=table('Equipment')
        for index,row in enumerate(rows,2):
            try:
                values=clean_values(t,row,creating=True);check_references(conn,t,values,user)
                values.update(CreatedBy=user['Id'],UpdatedBy=user['Id'])
                conn.execute(t.insert().values(**values))
            except HTTPException as ex: raise HTTPException(400,f'Строка {index}: {ex.detail}')
        return ok({'inserted':len(rows)},'Импорт завершён.')
    return mutation(request,user,{'file_hash':__import__('hashlib').sha256(content).hexdigest()},perform)

@router.get('/integrations/1c/status')
def integration(user=Depends(current_user)):
    return ok({'mode':'stub','connected':False,'message':'Учебная заглушка. Реальное подключение к 1С не настроено.'})
