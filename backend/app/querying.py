"""Shared UTC date and typed filter rules for lists, reports and analytics."""
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select
from .db import table
from .resources import ENUMS, scope


def utc_value(value, field='date'):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.astimezone(timezone.utc).replace(tzinfo=None) if result.tzinfo else result
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(400, f'Некорректная дата: {field}. Используйте ISO8601.')


def bounds(start=None, end=None, default=True, now=None):
    now = now or datetime.utcnow()
    begin = utc_value(start, 'from') if start else (now - timedelta(days=30) if default else None)
    finish = utc_value(end, 'to') if end else (now if default else None)
    if end and len(str(end)) == 10:
        try: finish += timedelta(days=1)  # A calendar end date includes that whole UTC day.
        except OverflowError: raise HTTPException(400,'Дата to выходит за поддерживаемый диапазон.')
    if begin and finish and finish <= begin:
        raise HTTPException(400, 'Дата to должна быть позже from.')
    if begin and finish and finish - begin > timedelta(days=3660):
        raise HTTPException(400, 'Период отчёта не должен превышать десять лет.')
    if default and begin and finish:
        try: begin - (finish-begin)
        except OverflowError: raise HTTPException(400,'Предыдущий период выходит за поддерживаемый диапазон дат.')
    return begin, finish


def workshop_ids(workshop_id=None, workshop_ids=None):
    try:
        values = {int(workshop_id)} if workshop_id is not None else set()
        if workshop_ids:
            values.update(int(part.strip()) for part in str(workshop_ids).split(','))
        if any(value <= 0 for value in values) or len(values) > 100:
            raise ValueError()
        return sorted(values)
    except (ValueError, TypeError):
        raise HTTPException(400, 'workshop_ids: ожидаются положительные ID через запятую.')


def clauses(t, user, workshop_id=None, workshop_ids_value=None, equipment_id=None,
            team_id=None, order_type=None, priority=None, start=None, end=None,
            hide_deleted=True):
    result = list(scope(t, user))
    if hide_deleted and 'IsDeleted' in t.c:
        result.append(t.c.IsDeleted == False)
    shops = workshop_ids(workshop_id, workshop_ids_value)
    equipment = table('Equipment')
    if shops:
        if t.name == 'Workshops':
            result.append(t.c.Id.in_(shops))
        elif 'WorkshopId' in t.c:
            result.append(t.c.WorkshopId.in_(shops))
        elif 'EquipmentId' in t.c:
            result.append(t.c.EquipmentId.in_(select(equipment.c.Id).where(equipment.c.WorkshopId.in_(shops))))
    if equipment_id is not None:
        try:
            ident = int(equipment_id)
            if ident <= 0: raise ValueError()
        except (ValueError, TypeError): raise HTTPException(400, 'Некорректный equipment_id.')
        if t.name == 'Equipment': result.append(t.c.Id == ident)
        elif 'EquipmentId' in t.c: result.append(t.c.EquipmentId == ident)
    if team_id is not None and 'TeamId' in t.c:
        result.append(t.c.TeamId == team_id)
    for value, column in ((order_type, 'Type'), (priority, 'Priority')):
        if value is not None:
            if value not in ENUMS[('WorkOrders', column)]:
                raise HTTPException(400, f'Недопустимое значение {column}.')
            if column in t.c: result.append(t.c[column] == value)
            elif t.name == 'MaintenanceSchedule':
                orders = table('WorkOrders')
                if column == 'Type':
                    if value != 'плановая': result.append(t.c.Id == -1)
                else:
                    result.append(t.c.Id.in_(select(orders.c.ScheduleId).where(orders.c.Priority == value)))
    begin, finish = bounds(start, end, default=False)
    date_name = 'PlannedAt' if t.name == 'MaintenanceSchedule' else 'CreatedAt' if 'CreatedAt' in t.c else None
    if date_name:
        if begin: result.append(t.c[date_name] >= begin)
        if finish: result.append(t.c[date_name] < finish)
    return result
