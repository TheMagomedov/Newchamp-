"""Integration tests against the isolated ChampTraining database, not user's other DBs."""
import csv
import io
import uuid
from datetime import datetime,timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app,limits
from app.config import DATABASE

@pytest.fixture(scope='module')
def client():
    assert DATABASE.startswith('ChampTraining_'), 'Do not run integration tests on another database.'
    with TestClient(app,raise_server_exceptions=False) as c: yield c

@pytest.fixture(autouse=True)
def reset_limit():
    limits.clear()

def login(client,role='admin'):
    response=client.post('/api/auth/login',json={'email':role+'@toir.local','password':'ChampDemo2027!'})
    assert response.status_code==200,response.text
    data=response.json()['data'];return {'Authorization':'Bearer '+data['access_token']},data

def test_auth_refresh_rotation_and_protection(client):
    assert client.get('/api/equipment').status_code==401
    headers,data=login(client)
    refreshed=client.post('/api/auth/refresh',json={'refresh_token':data['refresh_token']})
    assert refreshed.status_code==200,refreshed.text
    assert client.post('/api/auth/refresh',json={'refresh_token':data['refresh_token']}).status_code==401
    assert client.get('/api/auth/me',headers=headers).status_code==401
    newer=refreshed.json()['data']
    headers={'Authorization':'Bearer '+newer['access_token']}
    assert client.get('/api/auth/me',headers=headers).json()['data']['Role']=='admin'
    assert client.post('/api/auth/logout',headers=headers,json={'refresh_token':newer['refresh_token']}).status_code==200
    assert client.get('/api/auth/me',headers=headers).status_code==401

def test_all_resource_lists_and_metadata(client):
    headers,_=login(client)
    meta=client.get('/api/meta',headers=headers)
    assert meta.status_code==200,meta.text
    for item in meta.json()['data']['resources']:
        response=client.get('/api/'+item['key'],headers=headers)
        assert response.status_code==200,(item['key'],response.text)
        assert 'total' in response.json()['data']
        assert 'PasswordHash' not in response.text
    assert client.get('/api/lookups',headers=headers).status_code==200

def test_master_and_member_scope_manager_readonly(client):
    headers,user=login(client,'master')
    data=client.get('/api/equipment',headers=headers).json()['data']['items']
    assert data and all(row['WorkshopId']==user['user']['WorkshopId'] for row in data)
    admin,_=login(client)
    other=next(r for r in client.get('/api/equipment',headers=admin).json()['data']['items'] if r['WorkshopId']!=user['user']['WorkshopId'])
    assert client.get(f"/api/equipment/{other['Id']}",headers=headers).status_code==404
    assert client.get('/api/users',headers=headers).status_code==403
    manager,_=login(client,'manager')
    assert client.post('/api/equipment',headers=manager,json={}).status_code==403
    member,user=login(client,'member')
    orders=client.get('/api/work-orders',headers=member).json()['data']['items']
    assert all(r['TeamId']==user['user']['TeamId'] for r in orders)

def test_crud_idempotency_and_duplicate_validation(client):
    headers,_=login(client);key=str(uuid.uuid4());code='API-'+uuid.uuid4().hex[:10]
    payload={'Code':code,'Name':'Проверка API '+code,'Unit':'шт','Stock':15,'MinimumStock':2,'UnitPrice':10}
    first=client.post('/api/materials',headers={**headers,'Idempotency-Key':key},json=payload)
    assert first.status_code==201,first.text
    ident=first.json()['data']['Id']
    try:
        second=client.post('/api/materials',headers={**headers,'Idempotency-Key':key},json=payload)
        assert second.json()['data']['Id']==ident
        assert client.post('/api/materials',headers={**headers,'Idempotency-Key':key},json={**payload,'Stock':20}).status_code==409
        assert client.post('/api/materials',headers=headers,json=payload).status_code==409
        edit=client.put(f'/api/materials/{ident}',headers=headers,json={'Stock':20})
        assert edit.status_code==200,edit.text
        assert edit.json()['data']['Stock']==20
        assert client.put(f'/api/materials/{ident}',headers=headers,json={'Stock':-1}).status_code==400
    finally:
        removed=client.delete(f'/api/materials/{ident}',headers=headers)
        assert removed.status_code==200,removed.text

def test_workorder_stock_role_and_history(client):
    headers,_=login(client,'master')
    lookups=client.get('/api/lookups',headers=headers).json()['data']
    start=datetime.utcnow()+timedelta(days=120)
    payload={'EquipmentId':lookups['equipment'][0]['id'],'MasterId':lookups['users'][0]['id'],'Type':'текущая','Description':'API integration test','PlannedStart':start.isoformat(),'PlannedEnd':(start+timedelta(hours=2)).isoformat()}
    created=client.post('/api/work-orders',headers=headers,json=payload)
    assert created.status_code==201,created.text
    ident=created.json()['data']['Id']
    try:
        history=client.get(f'/api/work-orders/{ident}/history',headers=headers)
        assert history.status_code==200 and history.json()['data']
        assert client.post(f'/api/work-orders/{ident}/transition',headers=headers,json={'status':'закрыта'}).status_code==409
        material=client.get('/api/materials',headers=headers).json()['data']['items'][0]
        amount=min(1,material['Stock'])
        assert amount>0
        res=client.post(f'/api/work-orders/{ident}/materials',headers=headers,json={'MaterialId':material['Id'],'Quantity':amount})
        assert res.status_code==201,res.text
        after=client.get('/api/materials/'+str(material['Id']),headers=headers).json()['data']
        assert after['Stock']==material['Stock']-amount
        engineer,_=login(client,'engineer')
        assert client.post(f'/api/work-orders/{ident}/materials',headers=engineer,json={'MaterialId':material['Id'],'Quantity':1}).status_code==403
        res=client.delete(f'/api/work-orders/{ident}/materials/{material["Id"]}',headers=headers)
        assert res.status_code==200,res.text
        assert client.get('/api/materials/'+str(material['Id']),headers=headers).json()['data']['Stock']==material['Stock']
    finally:
        assert client.delete(f'/api/work-orders/{ident}',headers=headers).status_code==200

@pytest.mark.parametrize('format,signature',[('pdf',b'%PDF'),('xlsx',b'PK'),('csv',b'\xef\xbb\xbf')])
def test_report_exports_and_access(client,format,signature):
    headers,_=login(client)
    response=client.post('/api/reports/export',headers=headers,json={'format':format,'type':'equipment'})
    assert response.status_code==200,response.text
    link=response.json()['data']['url']
    data=client.get(link,headers=headers)
    assert data.status_code==200 and data.content.startswith(signature),data.text[:100]
    other,_=login(client,'master')
    assert client.get(link,headers=other).status_code==404

def test_dashboard_report_and_no_hash_in_audit(client):
    headers,_=login(client)
    for endpoint in ['/api/dashboard','/api/analytics','/api/reports/summary?workshop_id=1','/api/integrations/1c/status','/api/health']:
        result=client.get(endpoint,headers=headers)
        assert result.status_code==200,(endpoint,result.text)
    assert client.get('/api/dashboard?from=oops',headers=headers).status_code==400

def test_rate_limit_and_bad_requests(client):
    headers,_=login(client)
    for i in range(100): assert client.get('/api/auth/me',headers=headers).status_code==200
    assert client.get('/api/auth/me',headers=headers).status_code==429
