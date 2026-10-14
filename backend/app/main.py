import logging
import re
import threading
import time
from collections import defaultdict,deque
from contextlib import asynccontextmanager
from fastapi import FastAPI,Request,HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse,FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from . import config
from .db import engine,reflect
from .auth import router as auth_router,ok
from .api import router as data_router
from .reports import router as reports_router
from .advanced import router as advanced_router
from .security import decode_token

logging.basicConfig(filename=config.RUNTIME/'api.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',encoding='utf-8')
log=logging.getLogger('toir')
limits=defaultdict(deque);limit_lock=threading.Lock()

@asynccontextmanager
async def lifespan(app):
    if len(config.SECRET)<32: raise RuntimeError('Сначала выполните scripts/setup.py.')
    reflect()
    yield

app=FastAPI(title='ТОиР-Проф API',version='1.0.0',description='Учебное конкурсное решение: Python / SQL Server / WPF / Vue. Все даты серверных операций UTC. REST-клиенты не подключаются к БД напрямую.',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['GET','POST','PUT','DELETE','OPTIONS'],allow_headers=['Authorization','Content-Type','Idempotency-Key'],expose_headers=['Content-Disposition'])

def failure(status,message,code=None,headers=None):
    return JSONResponse({'success':False,'data':None,'message':message,'error_code':code or f'HTTP_{status}'},status_code=status,headers=headers)

@app.middleware('http')
async def guard(request:Request,call_next):
    if request.url.path.startswith('/api') and request.method!='OPTIONS':
        key='ip:'+str(request.client.host if request.client else 'local')
        if request.headers.get('Authorization','').startswith('Bearer '):
            try: key='user:'+decode_token(request.headers['Authorization'][7:])['sub']
            except Exception: pass
        maximum=20 if request.url.path=='/api/auth/login' else 100
        if request.url.path=='/api/auth/login': key+=':login'
        now=time.monotonic()
        with limit_lock:
            values=limits[key]
            while values and values[0]<now-60: values.popleft()
            if len(values)>=maximum: return failure(429,'Слишком много запросов. Повторите через минуту.',headers={'Retry-After':'60'})
            values.append(now)
    start=time.monotonic()
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    if request.url.path.startswith('/api'): response.headers['Cache-Control']='no-store'
    log.info('%s %s %s %.0fms',request.method,request.url.path,response.status_code,(time.monotonic()-start)*1000)
    return response

@app.exception_handler(HTTPException)
async def http_error(request,exc): return failure(exc.status_code,str(exc.detail),headers=exc.headers)
@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    fields=', '.join('.'.join(str(x) for x in err['loc']) for err in exc.errors())
    return failure(400,'Проверьте параметры: '+fields,'VALIDATION_ERROR')
@app.exception_handler(DBAPIError)
async def database_error(request,exc):
    source=str(exc.orig)
    business=re.search(r'\[SQL Server\](.*?)\s*\(510\d+\)',source,re.S)
    if business: message=business.group(1).strip()
    elif '2627' in source or '2601' in source: message='Такая запись уже существует. Проверьте уникальные номер, код, email и телефон.'
    elif '547' in source: message='Нарушено правило целостности: проверьте даты, статус, обязательные связи и допустимые значения.'
    else: message='Операция с БД не выполнена. Проверьте данные или доступность SQL Server.'
    log.warning('Database operation rejected: %s',type(exc.orig).__name__)
    return failure(409,message,'DATA_CONFLICT')
@app.exception_handler(Exception)
async def unhandled(request,exc):
    log.exception('Unexpected error type=%s',type(exc).__name__)
    return failure(500,'Внутренняя ошибка. Подробности сохранены в журнале сервера.','INTERNAL_ERROR')

@app.get('/api/health',tags=['Состояние'])
def health():
    with engine.connect() as conn: conn.execute(text('SELECT 1'))
    return ok({'status':'ok','database':config.DATABASE})

app.include_router(auth_router)
app.include_router(reports_router)
app.include_router(advanced_router)
app.include_router(data_router)
dist=config.ROOT/'web'/'dist'
if (dist/'assets').exists(): app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
@app.get('/{path:path}',include_in_schema=False)
def frontend(path:str):
    if path.startswith('api/'): raise HTTPException(404,'Метод API не найден.')
    if (dist/'index.html').exists(): return FileResponse(dist/'index.html')
    return {'message':'Соберите web: npm install && npm run build. API: /docs.'}
