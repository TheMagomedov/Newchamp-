"""Non-destructive bootstrap: creates a separate training database and demo accounts."""
import argparse
import re
import secrets
import sys
from datetime import datetime,timedelta
from pathlib import Path
import pyodbc

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
parser=argparse.ArgumentParser()
parser.add_argument('--database',default='ChampTraining_20261013')
args=parser.parse_args()
if not re.fullmatch(r'ChampTraining_[A-Za-z0-9_]+',args.database):
    raise SystemExit('Use a dedicated database name beginning ChampTraining_.')
env=ROOT/'.env'
if not env.exists():
    env.write_text(f'CHAMP_DATABASE={args.database}\nCHAMP_SERVER=localhost\nCHAMP_DRIVER=ODBC Driver 17 for SQL Server\nCHAMP_SECRET={secrets.token_urlsafe(48)}\n',encoding='utf-8')
from app.config import odbc,DATABASE
from app.security import hash_password
if DATABASE!=args.database: raise SystemExit('Existing .env names another database; align --database explicitly.')
with pyodbc.connect(odbc('master'),autocommit=True) as conn:
    exists=conn.execute('SELECT DB_ID(?)',DATABASE).fetchval()
    if not exists:
        conn.execute(f'CREATE DATABASE [{DATABASE}]')
        print('Created isolated training database:',DATABASE)
with pyodbc.connect(odbc(),autocommit=True) as conn:
    count=conn.execute('SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped=0').fetchval()
    if not count:
        for filename in ['01_schema.sql','02_rules.sql','03_seed.sql']:
            script=(ROOT/'database'/filename).read_text(encoding='utf-8-sig')
            for batch in re.split(r'^\s*GO\s*$',script,flags=re.M|re.I):
                if batch.strip():
                    cursor=conn.execute(batch)
                    while cursor.nextset(): pass
            print('Applied',filename)
    elif not conn.execute("SELECT OBJECT_ID('dbo.ClientRequests','U')").fetchval():
        raise SystemExit('Existing database is not this project. No changes made.')
    else:
        print('Existing training schema retained; no SQL/data reset.')

with pyodbc.connect(odbc()) as conn:
    roles=dict(conn.execute('SELECT Code,Id FROM dbo.Roles').fetchall())
    shop=conn.execute('SELECT MIN(Id) FROM dbo.Workshops').fetchval()
    team=conn.execute('SELECT MIN(Id) FROM dbo.Teams WHERE WorkshopId=?',shop).fetchval()
    for code,role_id in roles.items():
        email=code+'@toir.local'
        if conn.execute('SELECT Id FROM dbo.Users WHERE Email=?',email).fetchval(): continue
        conn.execute('INSERT dbo.Users(Email,Phone,LastName,FirstName,PasswordHash,RoleId,WorkshopId,TeamId) VALUES(?,?,?,?,?,?,?,?)',email,'+7000000000'+str(role_id),'Учебный',code,hash_password('ChampDemo2027!'),role_id,shop if code in ('master','member') else None,team if code=='member' else None)
    conn.commit()
    master=conn.execute("SELECT Id FROM dbo.Users WHERE Email='master@toir.local'").fetchval()
    actor=conn.execute("SELECT Id FROM dbo.Users WHERE Email='admin@toir.local'").fetchval()
    conn.execute("EXEC sys.sp_set_session_context @key=N'ActorId', @value=?",actor)
    if not conn.execute('SELECT COUNT(*) FROM dbo.WorkOrders').fetchval():
        equipment=[r[0] for r in conn.execute('SELECT Id FROM dbo.Equipment WHERE WorkshopId=? ORDER BY Id',shop)]
        mt=conn.execute("SELECT Id FROM dbo.MaintenanceTypes WHERE Code=N'TO-1'").fetchval()
        now=datetime.utcnow().replace(microsecond=0)
        for i in range(6):
            start=now-timedelta(days=10-i)
            created=start-timedelta(hours=1)
            cur=conn.execute('INSERT dbo.WorkOrders(EquipmentId,MaintenanceTypeId,MasterId,TeamId,Type,Priority,Description,PlannedStart,PlannedEnd,CreatedAt) VALUES(?,?,?,?,?,?,?,?,?,?); SELECT CAST(SCOPE_IDENTITY() AS int)',equipment[i%len(equipment)],mt,master,team,'текущая','высокий' if i==4 else 'средний',f'Учебная заявка {i+1}: диагностика и проверка оборудования',start,start+timedelta(hours=4),created)
            while cur.description is None: cur.nextset()
            ident=cur.fetchone()[0]
            if i<4:
                conn.execute("UPDATE dbo.WorkOrders SET Status=N'назначена' WHERE Id=?",ident)
                conn.execute("UPDATE dbo.WorkOrders SET Status=N'в работе',ActualStart=? WHERE Id=?",start,ident)
                if i<3:
                    conn.execute("UPDATE dbo.WorkOrders SET Status=N'выполнена',ActualEnd=?,CompletionReport=N'Учебная проверка завершена' WHERE Id=?",start+timedelta(hours=3),ident)
                if i<2: conn.execute("UPDATE dbo.WorkOrders SET Status=N'закрыта' WHERE Id=?",ident)
        conn.commit()
    print('Demo accounts: admin/master/engineer/member/manager @toir.local')
    print('Training-only password: ChampDemo2027!')
print('Ready. Run: .venv\\Scripts\\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000')
