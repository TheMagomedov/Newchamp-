from datetime import datetime,timedelta
from decimal import Decimal
import pytest
from app.domain import calculate_downtime,validate_work_order,calculate_total_material_cost

# Five public test functions, parameterized to cover the separate rubric scenarios.
@pytest.mark.parametrize('hours',[0,3,54,1.5,0.5,0.25])
def test_downtime_valid(hours):
    start=datetime(2027,1,1)
    assert calculate_downtime(start,start+timedelta(hours=hours))==hours

@pytest.mark.parametrize('start,end',[(None,datetime(2027,1,1)),(datetime(2027,1,1),None),(datetime(2027,1,2),datetime(2027,1,1))])
def test_downtime_invalid(start,end):
    with pytest.raises(ValueError): calculate_downtime(start,end)

def test_work_order_valid():
    assert validate_work_order({'EquipmentId':1,'Description':'Ремонт','Type':'аварийная','FailureReason':'Перегрев','PlannedStart':datetime(2027,1,1),'PlannedEnd':datetime(2027,1,2)})==[]

@pytest.mark.parametrize('override',[{'EquipmentId':None},{'Description':'  '},{'Type':'аварийная','FailureReason':''},
    {'PlannedEnd':datetime(2026,1,1)},{'PlannedStart':None},{'PlannedEnd':None},
    {'CreatedAt':datetime(2027,1,2)},{'ActualEnd':datetime(2027,1,2)},
    {'ActualStart':datetime(2027,1,2),'ActualEnd':datetime(2027,1,1)}])
def test_work_order_invalid(override):
    data={'EquipmentId':1,'Description':'Ремонт','Type':'текущая','PlannedStart':datetime(2027,1,1),'PlannedEnd':datetime(2027,1,2)}
    assert validate_work_order({**data,**override})

@pytest.mark.parametrize('rows,result',[([],Decimal('0')),([{'Quantity':4,'UnitPrice':850},{'Quantity':2,'UnitPrice':1200},{'Quantity':10,'UnitPrice':150}],Decimal('7300')),([{'Quantity':0,'UnitPrice':100}],Decimal('0')),([{'Quantity':-1,'UnitPrice':100}],None),([{'Quantity':1,'UnitPrice':-100}],None),
    ([{'Quantity':'0.125','UnitPrice':'1.20'}],Decimal('0.15')),
    ([{'Quantity':1,'UnitPrice':'NaN'}],None),([{'Quantity':'Infinity','UnitPrice':1}],None)])
def test_material_cost(rows,result):
    if result is None:
        with pytest.raises(ValueError): calculate_total_material_cost(rows)
    else: assert calculate_total_material_cost(rows)==result
