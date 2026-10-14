"""Scoped analytics from database records; no synthetic trends or sample KPI values."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import select
from .db import table, transaction
from .querying import bounds, clauses
from .resources import public

DONE = {'выполнена', 'закрыта'}
INACTIVE = DONE | {'отменена'}
DOWNTIME = {'в работе', 'ожидает материалов', 'выполнена', 'закрыта'}


def hours(start, end):
    return Decimal(str(max(0, (end - start).total_seconds()))) / Decimal(3600)


def downtime_interval(order, begin, finish, now):
    if not order.get('ActualStart') or order['Status'] not in DOWNTIME:
        return None
    a = max(order['ActualStart'], begin)
    b = min(order['ActualEnd'] or now, finish, now)
    return (a, b) if b > a else None


def numeric(value):
    return float(round(value, 2))


def change(current, previous):
    delta = current - previous
    return {'current': numeric(current), 'previous': numeric(previous), 'delta': numeric(delta),
            'percent': numeric(delta / abs(previous) * 100) if previous else None,
            'available': True}


def aggregate(data, begin, finish, now):
    """Pure calculation function, independently testable with fixed dates/Decimals."""
    equipment, orders, schedules = data['equipment'], data['orders'], data['schedule']
    equipment_map = {row['Id']: row for row in equipment}
    team_map = {row['Id']: row for row in data['teams']}
    shop_names = {row['Id']: row['Name'] for row in data['workshops']}
    material_map = {row['Id']: row for row in data['materials']}
    current_equipment = [row for row in equipment if not row.get('IsDeleted')]
    created = [row for row in orders if begin <= row['CreatedAt'] < finish]
    completed = [row for row in orders if row['Status'] in DONE and row['ActualEnd']
                 and begin <= row['ActualEnd'] < min(finish, now + timedelta(microseconds=1))]
    active = [row for row in orders if row['Status'] not in INACTIVE]
    overdue = [row for row in active if row['PlannedEnd'] < now]
    used = [row for row in data['usage'] if begin <= row['RecordedAt'] < min(finish, now + timedelta(microseconds=1))]
    previous_begin = begin - (finish - begin)
    previous_completed = [row for row in orders if row['Status'] in DONE and row['ActualEnd']
                          and previous_begin <= row['ActualEnd'] < min(begin, now + timedelta(microseconds=1))]
    previous_used = [row for row in data['usage'] if previous_begin <= row['RecordedAt'] < min(begin, now + timedelta(microseconds=1))]
    elapsed = [hours(row['ActualStart'], row['ActualEnd']) for row in completed if row['ActualStart']]
    previous_elapsed = [hours(row['ActualStart'], row['ActualEnd']) for row in previous_completed if row['ActualStart']]
    average = sum(elapsed, Decimal(0)) / len(elapsed) if elapsed else Decimal(0)
    previous_average = sum(previous_elapsed, Decimal(0)) / len(previous_elapsed) if previous_elapsed else Decimal(0)
    total_cost = sum((row['Quantity'] * row['UnitPrice'] for row in used), Decimal(0))
    previous_cost = sum((row['Quantity'] * row['UnitPrice'] for row in previous_used), Decimal(0))
    by_equipment = defaultdict(Decimal)
    total_downtime = previous_downtime = Decimal(0)
    # Charts use at most the last 30 calendar days of the requested period.
    last_day = (finish - timedelta(microseconds=1)).date()
    first_day = max(begin.date(), last_day - timedelta(days=29))
    days = [first_day + timedelta(days=i) for i in range((last_day - first_day).days + 1)]
    series = {day: {'date': day.isoformat(), 'created': 0, 'completed': 0,
                    'hours': Decimal(0), 'cost': Decimal(0)} for day in days}
    for row in created:
        if row['CreatedAt'].date() in series: series[row['CreatedAt'].date()]['created'] += 1
    for row in completed:
        if row['ActualEnd'].date() in series: series[row['ActualEnd'].date()]['completed'] += 1
    for row in orders:
        interval = downtime_interval(row, begin, finish, now)
        if interval:
            a, b = interval
            amount = hours(a, b)
            total_downtime += amount
            by_equipment[row['EquipmentId']] += amount
            for day in days:
                midnight = datetime.combine(day, datetime.min.time())
                start, end = max(a, midnight), min(b, midnight + timedelta(days=1))
                if end > start: series[day]['hours'] += hours(start, end)
        interval = downtime_interval(row, previous_begin, begin, now)
        if interval: previous_downtime += hours(*interval)
    material_totals = defaultdict(lambda: {'quantity': Decimal(0), 'cost': Decimal(0)})
    for row in used:
        value = row['Quantity'] * row['UnitPrice']
        material_totals[row['MaterialId']]['quantity'] += row['Quantity']
        material_totals[row['MaterialId']]['cost'] += value
        if row['RecordedAt'].date() in series: series[row['RecordedAt'].date()]['cost'] += value
    planned = [row for row in schedules if begin <= row['PlannedAt'] < finish and row['Status'] != 'отменено']
    linked_orders = {row['ScheduleId']: row for row in orders if row.get('ScheduleId')}

    def adherence(rows):
        finished = [row for row in rows if row['Status'] == 'выполнено']
        due = [row for row in rows if row['PlannedAt'] < now]
        def on_time(row):
            order = linked_orders.get(row['Id'])
            return bool(order and order['Status'] in DONE and order['ActualEnd']
                        and order['ActualEnd'] <= order['PlannedEnd'])
        ontime = sum(on_time(row) for row in rows)
        due_ontime = sum(on_time(row) for row in due)
        return {'planned': len(rows), 'completed': len(finished), 'on_time': ontime,
                'overdue': sum(row['Status'] != 'выполнено' for row in due), 'due': len(due),
                'adherence_percent': round(due_ontime / len(due) * 100, 2) if due else None}

    schedule_stats = adherence(planned)
    previous_planned = [row for row in schedules if previous_begin <= row['PlannedAt'] < begin and row['Status'] != 'отменено']
    previous_adherence = adherence(previous_planned)['adherence_percent']
    current_adherence = schedule_stats['adherence_percent']
    schedule_stats['trend'] = (change(Decimal(str(current_adherence)), Decimal(str(previous_adherence)))
        if current_adherence is not None and previous_adherence is not None else
        {'current':current_adherence,'previous':previous_adherence,'delta':None,'percent':None,
         'available':False,'reason':'Нет наступивших плановых ТО в одном из сравниваемых периодов.'})
    schedule_stats['by_workshop'] = []
    for shop_id, label in shop_names.items():
        subset = [row for row in planned if equipment_map.get(row['EquipmentId'], {}).get('WorkshopId') == shop_id]
        if subset:
            schedule_stats['by_workshop'].append({'workshop_id': shop_id, 'label': label, **adherence(subset)})
    rankings = []
    for team_id, team in team_map.items():
        finished = [row for row in completed if row['TeamId'] == team_id]
        open_rows = [row for row in active if row['TeamId'] == team_id]
        durations = [hours(row['ActualStart'], row['ActualEnd']) for row in finished if row['ActualStart']]
        rankings.append({'team_id': team_id, 'label': team['Name'], 'completed': len(finished),
                         'active': len(open_rows),
                         'avg_completion_hours': numeric(sum(durations, Decimal(0)) / len(durations)) if durations else None,
                         'on_time_percent': round(sum(row['ActualEnd'] <= row['PlannedEnd'] for row in finished) / len(finished) * 100, 2) if finished else None,
                         'planned_hours': numeric(sum((hours(row['PlannedStart'], row['PlannedEnd']) for row in open_rows), Decimal(0)))})
    rankings.sort(key=lambda row: (-row['completed'], -(row['on_time_percent'] or 0), row['label']))

    def enriched(row):
        value = public(row)
        eq = equipment_map.get(row.get('EquipmentId'), {})
        value['EquipmentName'] = eq.get('Name')
        value['WorkshopName'] = shop_names.get(eq.get('WorkshopId'))
        value['TeamName'] = team_map.get(row.get('TeamId'), {}).get('Name')
        return value

    low = [row for row in data['materials'] if row['Stock'] <= row['MinimumStock']]
    workshop_counts = Counter(equipment_map[row['EquipmentId']]['WorkshopId'] for row in created if row['EquipmentId'] in equipment_map)
    downtime_all = [{'equipment_id':key,'inventory_number':equipment_map[key]['InventoryNumber'],
                     'label':equipment_map[key]['Name'],'workshop_id':equipment_map[key]['WorkshopId'],'hours':numeric(value)}
                    for key,value in sorted(by_equipment.items(),key=lambda item:(-item[1],item[0])) if key in equipment_map]
    materials_all = [{'material_id':key,'code':material_map[key]['Code'],'label':material_map[key]['Name'],
                      'unit':material_map[key]['Unit'],'quantity':float(value['quantity']),'cost':numeric(value['cost'])}
                     for key,value in sorted(material_totals.items(),key=lambda item:(-item[1]['cost'],item[0]))]
    return {
        'metrics': {'equipment': len(current_equipment), 'repair_equipment': sum(row['Status'] == 'в ремонте' for row in current_equipment),
                    'open_orders': len(active), 'overdue': len(overdue), 'low_stock': len(low),
                    'downtime_hours': numeric(total_downtime), 'today_orders': sum(row['CreatedAt'].date() == now.date() for row in orders),
                    'avg_completion_hours': numeric(average) if elapsed else None, 'completed_orders': len(completed),
                    'material_cost': numeric(total_cost)},
        'trends': {'downtime_hours': change(total_downtime, previous_downtime),
                   'completed_orders': change(Decimal(len(completed)), Decimal(len(previous_completed))),
                   'material_cost': change(total_cost, previous_cost),
                   'avg_completion_hours': change(average, previous_average) if elapsed and previous_elapsed else
                       {'current': numeric(average) if elapsed else None, 'previous': numeric(previous_average) if previous_elapsed else None,
                        'delta': None, 'percent': None, 'available': False, 'reason': 'Нет завершённых заявок в одном из периодов.'}},
        'kpi_trends': {key: {'available': False, 'reason': 'Исторические снимки текущего состояния не сохранялись.'}
                       for key in ('equipment', 'repair_equipment', 'open_orders', 'overdue', 'low_stock')},
        'equipment_status': [{'label': key, 'value': value} for key, value in Counter(row['Status'] for row in current_equipment).items()],
        'orders_by_status': [{'label': key, 'value': value} for key, value in Counter(row['Status'] for row in created).items()],
        'orders_by_type': [{'label': key, 'value': value} for key, value in Counter(row['Type'] for row in created).items()],
        'orders_by_priority': [{'label': key, 'value': value} for key, value in Counter(row['Priority'] for row in created).items()],
        'orders_by_workshop': [{'workshop_id': key, 'label': shop_names.get(key), 'value': value} for key, value in workshop_counts.items()],
        'by_workshop': [{'label': shop_names.get(key), 'value': value} for key, value in Counter(row['WorkshopId'] for row in current_equipment).items()],
        'orders_daily': [{key: row[key] for key in ('date', 'created', 'completed')} for row in series.values()],
        'downtime_daily': [{'date': row['date'], 'hours': numeric(row['hours'])} for row in series.values()],
        'materials_daily': [{'date': row['date'], 'cost': numeric(row['cost'])} for row in series.values()],
        'top_downtime': downtime_all[:10], 'downtime_all': downtime_all,
        'materials_top': materials_all[:10], 'materials_all': materials_all,
        'schedule': schedule_stats, 'team_rankings': rankings,
        'recent_orders': [enriched(row) for row in sorted(created, key=lambda row: row['Id'], reverse=True)[:10]],
        'active_orders': [enriched(row) for row in sorted(active, key=lambda row: row['PlannedEnd'])[:10]],
        'upcoming': [enriched(row) for row in sorted(schedules, key=lambda row: row['PlannedAt'])
                     if row['Status'] not in ('выполнено', 'отменено') and now <= row['PlannedAt'] < now + timedelta(days=7)][:10],
        'low_stock': [public(row) for row in low[:20]],
        'period': {'from': begin.isoformat(), 'to': finish.isoformat(), 'timeline_from': first_day.isoformat(),
                   'previous_from': previous_begin.isoformat(), 'previous_to': begin.isoformat()},
        'calculated_at': now.isoformat(),
    }


def load_data(conn, user, workshop_id=None, workshop_ids=None, order_type=None, priority=None, equipment_id=None):
    e, o, s = (table(name) for name in ('Equipment', 'WorkOrders', 'MaintenanceSchedule'))
    common = dict(workshop_id=workshop_id, workshop_ids_value=workshop_ids, equipment_id=equipment_id)
    order_clauses = clauses(o, user, **common, order_type=order_type, priority=priority)
    data = {
        'equipment': [dict(row) for row in conn.execute(select(e).where(*clauses(e, user, **common, hide_deleted=False))).mappings()],
        'orders': [dict(row) for row in conn.execute(select(o).where(*order_clauses)).mappings()],
        'schedule': [dict(row) for row in conn.execute(select(s).where(*clauses(s, user, **common))).mappings()],
    }
    if order_type and order_type != 'плановая': data['schedule'] = []
    if priority:
        included_schedule_ids = {row['ScheduleId'] for row in data['orders'] if row['ScheduleId']}
        data['schedule'] = [row for row in data['schedule'] if row['Id'] in included_schedule_ids]
    for key, name in (('materials', 'Materials'), ('teams', 'Teams'), ('workshops', 'Workshops')):
        t = table(name)
        data[key] = [dict(row) for row in conn.execute(select(t).where(*clauses(t, user, workshop_id, workshop_ids))).mappings()]
    usage = table('WorkOrderMaterials')
    data['usage'] = [dict(row) for row in conn.execute(select(usage).join(o, o.c.Id == usage.c.WorkOrderId).where(*order_clauses)).mappings()]
    return data


def summary(user, start=None, end=None, workshop_id=None, workshop_ids=None, order_type=None, priority=None, equipment_id=None):
    now = datetime.utcnow()
    begin, finish = bounds(start, end, now=now)
    with transaction(user['Id']) as conn:
        data = load_data(conn, user, workshop_id, workshop_ids, order_type, priority, equipment_id)
    return aggregate(data, begin, finish, now)
