"""Регрессии API: сортировка, склад, импорт и полный жизненный цикл заявки."""
import csv
import io
import uuid
from datetime import datetime,timedelta
from test_api import client,login,reset_limit


def test_sort_directions_id_and_stable_ties(client):
    headers,_=login(client)
    prefix='SORT-'+uuid.uuid4().hex[:10]
    created=[]
    try:
        for suffix in ('C','A','B'):
            response=client.post('/api/materials',headers=headers,json={
                'Code':prefix+'-'+suffix,'Name':prefix+' common name','Unit':'шт',
                'Stock':5,'MinimumStock':1,'UnitPrice':10})
            assert response.status_code==201,response.text
            created.append(response.json()['data'])
        for field in ('Id','Code'):
            for direction in ('asc','desc'):
                response=client.get('/api/materials',headers=headers,params={
                    'search':prefix,'sort_by':field,'sort_dir':direction,'page_size':10})
                assert response.status_code==200,response.text
                actual=response.json()['data']
                assert actual['total']==3
                expected=sorted(created,key=lambda row:row[field],reverse=direction=='desc')
                assert [row['Id'] for row in actual['items']]==[row['Id'] for row in expected]
        # Equal names must have deterministic Id ordering, including across pages.
        pages=[client.get('/api/materials',headers=headers,params={
            'search':prefix,'sort_by':'Name','sort_dir':'desc','page':page,'page_size':1})
            for page in (1,2,3)]
        assert all(response.status_code==200 for response in pages)
        assert [response.json()['data']['items'][0]['Id'] for response in pages]==sorted(row['Id'] for row in created)
    finally:
        for row in created:
            response=client.delete('/api/materials/'+str(row['Id']),headers=headers)
            assert response.status_code==200,response.text

def test_sort_rejects_unknown_sensitive_fields_and_invalid_direction(client):
    headers,_=login(client)
    cases=[('/api/materials',{'sort_by':'MissingColumn'}),
           ('/api/materials',{'sort_by':'Id; DROP TABLE Materials'}),
           ('/api/materials',{'sort_dir':'sideways'}),
           ('/api/users',{'sort_by':'PasswordHash'}),
           ('/api/work-orders',{'sort_by':'Version'})]
    for endpoint,params in cases:
        response=client.get(endpoint,headers=headers,params=params)
        assert response.status_code==400,(params,response.text)
        assert response.json()['success'] is False
    assert client.get('/api/materials',headers=headers,params={'sort_by':'Id','sort_dir':'asc'}).status_code==200

def test_catalog_cannot_decrease_stock_even_with_other_field_changes(client):
    admin,_=login(client)
    code='STOCK-'+uuid.uuid4().hex[:10]
    response=client.post('/api/materials',headers=admin,json={
        'Code':code,'Name':'Stock regression '+code,'Unit':'кг','Stock':12.5,
        'MinimumStock':1,'UnitPrice':20})
    assert response.status_code==201,response.text
    original=response.json()['data'];ident=original['Id']
    try:
        engineer,_=login(client,'engineer')
        for headers in (admin,engineer):
            rejected=client.put(f'/api/materials/{ident}',headers=headers,
                json={'Stock':12,'Name':'Must not be saved'})
            assert rejected.status_code==400,rejected.text
            unchanged=client.get(f'/api/materials/{ident}',headers=admin).json()['data']
            assert unchanged['Stock']==12.5
            assert unchanged['Name']==original['Name']
    finally:
        response=client.delete(f'/api/materials/{ident}',headers=admin)
        assert response.status_code==200,response.text

def test_equipment_import_rolls_back_valid_first_row_when_second_is_invalid(client):
    from sqlalchemy import select
    from app.db import table,transaction
    headers,_=login(client)
    workshop=client.get('/api/lookups',headers=headers).json()['data']['workshops'][0]['id']
    prefix='IMPORT-'+uuid.uuid4().hex[:10]
    codes=[prefix+'-GOOD',prefix+'-BAD']
    output=io.StringIO()
    writer=csv.writer(output,delimiter=';')
    writer.writerow(['InventoryNumber','Name','Model','WorkshopId','CommissionedOn','StartedOn'])
    writer.writerow([codes[0],'Valid import fixture','Test',workshop,'2020-01-01','2020-01-02'])
    writer.writerow([codes[1],'Invalid import fixture','Test',workshop,'2020-01-01','not-a-date'])
    equipment=table('Equipment')
    try:
        response=client.post('/api/import/equipment',headers={**headers,'Content-Type':'text/csv'},
            params={'filename':'rollback.csv'},content=output.getvalue().encode('utf-8'))
        assert response.status_code==400,response.text
        assert response.json()['success'] is False
        assert 'Строка 3' in response.json()['message']
        # Query all rows, including soft-deleted ones, to prove transaction atomicity.
        with transaction() as conn:
            persisted=conn.execute(select(equipment.c.Id).where(equipment.c.InventoryNumber.in_(codes))).all()
        assert persisted==[],persisted
    finally:
        # Only this test's two random inventory numbers can be cleaned up on failure.
        with transaction() as conn:
            conn.execute(equipment.delete().where(equipment.c.InventoryNumber.in_(codes)))

def test_full_workorder_lifecycle_with_material_and_rounded_created_time(client,monkeypatch):
    import app.api as api_module
    from app.db import table,transaction
    headers,session=login(client,'master')
    master=session['user']
    prefix='CYCLE-'+uuid.uuid4().hex[:10]
    own={}
    try:
        fixtures=[('equipment',{'InventoryNumber':prefix,'Name':prefix,'Model':'Test',
                    'WorkshopId':master['WorkshopId'],'CommissionedOn':'2020-01-01','StartedOn':'2020-01-02'}),
                  ('teams',{'Code':prefix,'Name':prefix,'Specialization':'Test','WorkshopId':master['WorkshopId']}),
                  ('materials',{'Code':prefix,'Name':prefix,'Unit':'кг','Stock':5,'MinimumStock':1,'UnitPrice':90})]
        for resource,payload in fixtures:
            response=client.post('/api/'+resource,headers=headers,json=payload)
            assert response.status_code==201,response.text
            own[resource]=response.json()['data']['Id']
        planned=datetime.utcnow()+timedelta(minutes=5)
        response=client.post('/api/work-orders',headers=headers,json={
            'EquipmentId':own['equipment'],'MasterId':master['Id'],'Type':'текущая',
            'Description':prefix,'PlannedStart':planned.isoformat(),
            'PlannedEnd':(planned+timedelta(hours=1)).isoformat()})
        assert response.status_code==201,response.text
        order=response.json()['data'];own['work-orders']=order['Id']
        endpoint=f'/api/work-orders/{order["Id"]}'

        def transition(status,**values):
            result=client.post(endpoint+'/transition',headers=headers,json={'status':status,**values})
            assert result.status_code==200,(status,result.text)
            updated=result.json()['data']
            assert updated['Status']==status
            return updated

        transition('назначена',team_id=own['teams'])
        # Reproduce SQL datetime2(0) rounding: real .750s becomes next second,
        # while the old API floor returned the preceding second on immediate start.
        clock=[datetime.fromisoformat(order['CreatedAt'])-timedelta(microseconds=250000)]
        class SimulatedDateTime(datetime):
            @classmethod
            def utcnow(cls): return clock[0]
        monkeypatch.setattr(api_module,'datetime',SimulatedDateTime)
        started=transition('в работе')
        assert datetime.fromisoformat(started['ActualStart'])>=datetime.fromisoformat(order['CreatedAt'])
        result=client.post(endpoint+'/materials',headers=headers,json={
            'MaterialId':own['materials'],'Quantity':1.25,'Comment':'Lifecycle regression'})
        assert result.status_code==201,result.text
        transition('ожидает материалов')
        resumed=transition('в работе')
        assert resumed['ActualStart']==started['ActualStart']
        clock[0]=datetime.fromisoformat(started['ActualStart'])+timedelta(seconds=2)
        completed=transition('выполнена',completion_report='Ремонт завершён, оборудование проверено.')
        assert datetime.fromisoformat(completed['ActualEnd'])>datetime.fromisoformat(completed['ActualStart'])
        transition('закрыта')
        history=client.get(endpoint+'/history',headers=headers).json()['data']
        assert [row['NewStatus'] for row in reversed(history)]==[
            'создана','назначена','в работе','ожидает материалов','в работе','выполнена','закрыта']
        materials=client.get(endpoint+'/materials',headers=headers).json()['data']
        assert len(materials)==1 and materials[0]['Quantity']==1.25 and materials[0]['UnitPrice']==90
        assert client.get('/api/materials/'+str(own['materials']),headers=headers).json()['data']['Stock']==3.75
        assert client.delete(endpoint,headers=headers).status_code==409
    finally:
        # API intentionally cannot delete closed orders. Remove only exact fixture IDs.
        with transaction() as conn:
            for resource,name in [('work-orders','WorkOrders'),('equipment','Equipment'),
                                  ('teams','Teams'),('materials','Materials')]:
                if resource in own:
                    t=table(name)
                    conn.execute(t.delete().where(t.c.Id==own[resource]))
