from datetime import datetime
from decimal import Decimal

def calculate_downtime(start, end):
    if start is None or end is None:
        raise ValueError('Обе даты обязательны.')
    if end < start:
        raise ValueError('Дата окончания не может быть раньше начала.')
    return (end-start).total_seconds()/3600

def validate_work_order(data):
    errors=[]
    if not data.get('EquipmentId'): errors.append('Оборудование обязательно.')
    if not str(data.get('Description','')).strip(): errors.append('Описание обязательно.')
    if data.get('Type')=='аварийная' and not str(data.get('FailureReason') or '').strip(): errors.append('Причина обязательна для аварийной заявки.')
    start,end=data.get('PlannedStart'),data.get('PlannedEnd')
    if not start: errors.append('Плановая дата начала обязательна.')
    if not end: errors.append('Плановая дата окончания обязательна.')
    if start and end and end<=start: errors.append('Плановая дата окончания должна быть позже начала.')
    created=data.get('CreatedAt')
    if created and start and start<created: errors.append('Плановое начало не может быть раньше создания.')
    actual_start,actual_end=data.get('ActualStart'),data.get('ActualEnd')
    if actual_end and not actual_start: errors.append('Фактическое начало обязательно при завершении.')
    if actual_start and actual_end and actual_end<=actual_start: errors.append('Фактическое окончание должно быть позже начала.')
    if created and actual_start and actual_start<created: errors.append('Фактическое начало не может быть раньше создания.')
    return errors

def calculate_total_material_cost(materials):
    total=Decimal('0')
    for item in materials:
        quantity=Decimal(str(item['Quantity']))
        price=Decimal(str(item['UnitPrice']))
        if not quantity.is_finite() or not price.is_finite(): raise ValueError('Количество и цена должны быть конечными числами.')
        if quantity<0 or price<0: raise ValueError('Количество и цена не могут быть отрицательными.')
        total+=quantity*price
    return total.quantize(Decimal('0.01'))
