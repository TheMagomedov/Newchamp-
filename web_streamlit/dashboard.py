"""Фильтры, шесть KPI и обзор. Автообновление — polling, не SSE."""
from datetime import date, timedelta

import streamlit as st

from analytics_sections import render_sections
from charts import chart
from common import choices, export_control, fetch, fmt, navigate, table, utc_now


def filters_panel(lookups):
    today = utc_now().date()
    defaults = {'from': (today - timedelta(days=29)).isoformat(), 'to': today.isoformat()}
    applied = st.session_state.setdefault('analytics_filters', defaults)
    pending = st.session_state.pop('pending_analytics_filters', None)
    if pending is not None:
        st.session_state['analytics_filters'] = applied = pending
        st.session_state['analytics-from'] = date.fromisoformat(pending['from'])
        st.session_state['analytics-to'] = date.fromisoformat(pending['to'])
        st.session_state['analytics-workshops'] = [int(value) for value in
            pending.get('workshop_ids', '').split(',') if value]
        st.session_state['analytics-equipment'] = pending.get('equipment_id')
        st.session_state['analytics-type'] = pending.get('type', '')
        st.session_state['analytics-priority'] = pending.get('priority', '')
    with st.expander('Период и фильтры', expanded=False):
        with st.form('analytics-filters'):
            columns = st.columns(2)
            start = columns[0].date_input('Период с', today - timedelta(days=29), key='analytics-from')
            end = columns[1].date_input('Период по', today, key='analytics-to')
            shops = choices(lookups, 'workshops')
            selected = st.multiselect('Цеха: можно выбрать несколько', list(shops),
                                      format_func=shops.get, key='analytics-workshops')
            equipment = choices(lookups, 'equipment')
            ident = st.selectbox('Оборудование', [None, *equipment],
                                 format_func=lambda item: equipment.get(item, 'Всё оборудование'),
                                 key='analytics-equipment')
            order_type = st.selectbox('Тип заявки', ['', 'плановая', 'текущая', 'аварийная'],
                                      format_func=lambda value: value or 'Все типы', key='analytics-type')
            priority = st.selectbox('Приоритет', ['', 'низкий', 'средний', 'высокий', 'критический'],
                                    format_func=lambda value: value or 'Все приоритеты', key='analytics-priority')
            submitted = st.form_submit_button('Применить фильтры', type='primary')
        if submitted:
            if start > end:
                st.error('Начало периода должно быть не позже окончания.')
            else:
                values = {'from': start.isoformat(), 'to': end.isoformat(),
                          'workshop_ids': ','.join(map(str, selected)), 'equipment_id': ident,
                          'type': order_type, 'priority': priority}
                applied = {key: value for key, value in values.items() if value not in ('', None)}
                st.session_state['analytics_filters'] = applied
        templates = st.session_state.setdefault('filter_templates', {})
        name = st.text_input('Название шаблона', key='template-name')
        if st.button('Сохранить применённые фильтры', disabled=not name.strip()):
            templates[name.strip()] = dict(applied)
            st.success('Шаблон сохранён в текущей сессии.')
        if templates:
            selected_name = st.selectbox('Сохранённые шаблоны', list(templates))
            if st.button('Загрузить шаблон'):
                st.session_state['pending_analytics_filters'] = dict(templates[selected_name])
                st.rerun()
        if st.button('Сбросить фильтры'):
            st.session_state['pending_analytics_filters'] = defaults
            st.rerun()
    st.caption('Применены: ' + ', '.join(f'{key}={value}' for key, value in applied.items()))
    return applied


def metrics(data):
    values = data.get('metrics', {})
    schedule = data.get('schedule', {})
    specifications = [
        ('equipment', 'Оборудование', values.get('equipment')),
        ('open_orders', 'Активные заявки', values.get('open_orders')),
        ('completed_orders', 'Выполненные заявки', values.get('completed_orders')),
        ('downtime_hours', 'Простои, ч', values.get('downtime_hours')),
        ('avg_completion_hours', 'Среднее время, ч', values.get('avg_completion_hours')),
        ('adherence_percent', 'Выполнение ТО, %', schedule.get('adherence_percent')),
    ]
    for offset in (0, 3):
        for column, (key, title, value) in zip(st.columns(3), specifications[offset:offset + 3]):
            trend = data.get('trends', {}).get(key, data.get('kpi_trends', {}).get(key, {}))
            delta = None
            if trend.get('available') and trend.get('percent') is not None:
                delta = f"{trend['percent']:+.1f}% к предыдущему периоду"
            column.metric(title, fmt(value), delta)
            if not delta:
                column.caption(trend.get('reason', 'Нет данных для сравнения.'))


def scoped_target(resource, filters, row=None, extra=None, ident=None):
    selected = dict(filters)
    if resource not in ('schedule', 'work-orders'):
        selected = {key: value for key, value in selected.items()
                    if key in ('workshop_ids', 'equipment_id')}
    selected.update(extra or {})
    navigate(resource, ident, selected)


@st.fragment(run_every='60s')
def live_dashboard(client, filters, analytics, lookups):
    st.button('Обновить показатели', key='refresh-dashboard')
    data = fetch(client, 'analytics/dashboard', filters)
    if data is None:
        return
    st.caption('Связь с API есть · обновление раз в 60 секунд (polling, не SSE).')
    metrics(data)
    left, right = st.columns(2)
    with left:
        chart('Оборудование по статусам', data.get('equipment_status', []), 'equipment-status',
              kind='pie', target=lambda row: scoped_target('equipment', filters,
              extra={'status': row['label']}))
    with right:
        chart('Заявки по цехам', data.get('orders_by_workshop', []), 'orders-workshops',
              target=lambda row: scoped_target('work-orders', filters,
              extra={'workshop_ids': str(row['workshop_id'])}))
    if analytics:
        render_sections(client, data, filters, lookups)
    else:
        chart('Динамика заявок: последние 30 дней периода', data.get('orders_daily', []),
              'orders-daily', label='date', value='created', kind='line')
        chart('Топ-5 простоев', data.get('top_downtime', [])[:5], 'downtime-top5', value='hours',
              target=lambda row: navigate('equipment', row['equipment_id']))
        st.subheader('10 последних заявок')
        table(data.get('recent_orders', []), {'Number': 'Заявка', 'EquipmentName': 'Оборудование',
              'Status': 'Статус', 'Priority': 'Приоритет', 'CreatedAt': 'Создано'}, 'recent-orders',
              target=lambda row: navigate('work-orders', row['Id']))
        notifications = fetch(client, 'notifications', default={'items': []})
        st.subheader('Нарушения и просрочки')
        table(notifications.get('items', []), {'title': 'Событие', 'message': 'Подробности'},
              'violations', target=lambda row: navigate(row['resource'], row['entity_id']))
    export_control(client, 'analytics', filters, 'analytics-all', 'all')


def render(client, lookups, analytics=False):
    st.header('Аналитика обслуживания' if analytics else 'Обзор предприятия')
    filters = filters_panel(lookups)
    live_dashboard(client, filters, analytics, lookups)
