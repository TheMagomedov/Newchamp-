from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from fastapi import HTTPException
from app.analytics import aggregate, downtime_interval
from app.querying import bounds, workshop_ids


def dataset():
    return {'equipment':[{'Id':1,'Name':'Пресс','InventoryNumber':'П-1','WorkshopId':1,'Status':'в ремонте','IsDeleted':False}],
            'orders':[], 'schedule':[], 'teams':[{'Id':1,'Name':'Бригада'}],
            'workshops':[{'Id':1,'Name':'Цех'}], 'materials':[
                {'Id':1,'Name':'Масло','Code':'М-1','Unit':'л','Stock':Decimal('1'),'MinimumStock':Decimal('2')}], 'usage':[]}


def order(**values):
    return {'Id':1,'EquipmentId':1,'TeamId':1,'ScheduleId':None,'Type':'плановая','Priority':'высокий',
            'CreatedAt':datetime(2026,10,10),'PlannedStart':datetime(2026,10,10,1),
            'PlannedEnd':datetime(2026,10,10,5),'ActualStart':datetime(2026,10,10,1),
            'ActualEnd':datetime(2026,10,10,3),'Status':'выполнена',**values}


def test_downtime_clips_to_requested_period_and_current_time():
    now=datetime(2026,10,11,1)
    data=dataset()
    data['orders']=[order(Status='в работе',ActualStart=datetime(2026,10,10,22),ActualEnd=None)]
    result=aggregate(data,datetime(2026,10,10,23),datetime(2026,10,12),now)
    assert result['metrics']['downtime_hours']==2
    assert result['top_downtime'][0]['hours']==2
    assert result['downtime_daily']==[{'date':'2026-10-10','hours':1},{'date':'2026-10-11','hours':1}]
    assert downtime_interval(data['orders'][0],datetime(2026,10,12),datetime(2026,10,13),now) is None


def test_decimal_consumption_uses_historical_price_not_catalog_price():
    data=dataset();data['orders']=[order()]
    data['materials'][0]['UnitPrice']=Decimal('9999')
    data['usage']=[{'MaterialId':1,'Quantity':Decimal('0.125'),'UnitPrice':Decimal('1.20'),
                    'RecordedAt':datetime(2026,10,10,4)},
                   {'MaterialId':1,'Quantity':Decimal('0.2'),'UnitPrice':Decimal('0.10'),
                    'RecordedAt':datetime(2026,10,10,5)}]
    result=aggregate(data,datetime(2026,10,10),datetime(2026,10,11),datetime(2026,10,12))
    assert result['metrics']['material_cost']==0.17
    assert result['materials_top'][0]['quantity']==0.325
    assert result['metrics']['avg_completion_hours']==2
    assert result['trends']['material_cost']['previous']==0
    assert result['trends']['material_cost']['percent'] is None
    assert result['trends']['avg_completion_hours']['available'] is False


def test_schedule_adherence_and_comparable_previous_period():
    data=dataset()
    data['orders']=[order(ScheduleId=1),order(Id=2,ScheduleId=2,CreatedAt=datetime(2026,10,9),
        PlannedStart=datetime(2026,10,9,1),PlannedEnd=datetime(2026,10,9,2),
        ActualStart=datetime(2026,10,9,1),ActualEnd=datetime(2026,10,9,3))]
    data['schedule']=[{'Id':1,'EquipmentId':1,'TeamId':1,'PlannedAt':datetime(2026,10,10,1),'Status':'выполнено'},
                      {'Id':2,'EquipmentId':1,'TeamId':1,'PlannedAt':datetime(2026,10,9,1),'Status':'выполнено'},
                      {'Id':3,'EquipmentId':1,'TeamId':1,'PlannedAt':datetime(2026,10,10,3),'Status':'отменено'}]
    result=aggregate(data,datetime(2026,10,10),datetime(2026,10,11),datetime(2026,10,12))
    assert result['schedule']['planned']==1
    assert result['schedule']['adherence_percent']==100
    assert result['schedule']['trend']['previous']==0
    assert result['schedule']['trend']['delta']==100
    assert result['team_rankings'][0]['completed']==1
    assert result['team_rankings'][0]['on_time_percent']==100


def test_empty_period_has_no_invented_average_or_adherence():
    result=aggregate(dataset(),datetime(2026,10,10),datetime(2026,10,11),datetime(2026,10,12))
    assert result['metrics']['avg_completion_hours'] is None
    assert result['metrics']['downtime_hours']==0
    assert result['schedule']['adherence_percent'] is None
    assert result['schedule']['trend']['available'] is False
    assert result['kpi_trends']['equipment']['available'] is False
    assert result['upcoming']==[]


def test_report_data_keeps_all_equipment_while_chart_limits_top_ten():
    data=dataset()
    for ident in range(1,13):
        if ident>1: data['equipment'].append({**data['equipment'][0],'Id':ident,'InventoryNumber':str(ident)})
        data['orders'].append(order(Id=ident,EquipmentId=ident))
    result=aggregate(data,datetime(2026,10,10),datetime(2026,10,11),datetime(2026,10,12))
    assert len(result['top_downtime'])==10
    assert len(result['downtime_all'])==12
    assert sum(row['hours'] for row in result['downtime_all'])==24


def test_utc_date_filters_are_inclusive_for_calendar_end_only():
    begin,end=bounds('2026-10-10','2026-10-10')
    assert begin==datetime(2026,10,10) and end==datetime(2026,10,11)
    begin,end=bounds('2026-10-10T03:00:00+03:00','2026-10-10T06:00:00+03:00')
    assert begin==datetime(2026,10,10) and end==datetime(2026,10,10,3)
    assert workshop_ids(2,'1,2,3')==[1,2,3]


@pytest.mark.parametrize('start,end',[('bad','2026-10-11'),('2026-10-12','2026-10-10'),('2000-01-01','2026-10-10'),
    ('9999-12-30','9999-12-31'),('0001-01-01','0001-01-02')])
def test_invalid_date_filters_are_rejected(start,end):
    with pytest.raises(HTTPException) as caught: bounds(start,end)
    assert caught.value.status_code==400
