"""Фрагмент: месячный календарь ТО и создание связанной плановой заявки."""
import calendar
from datetime import date, datetime, timedelta

import streamlit as st

from api_client import ApiError
from common import choices, error_message, lookup_input, navigate, utc_now

STATUSES = ['запланировано', 'назначено', 'выполняется', 'выполнено', 'отменено', 'просрочено']
ICONS = {'запланировано': '🔵', 'назначено': '🟡', 'выполняется': '🟠',
         'выполнено': '🟢', 'отменено': '⚪', 'просрочено': '🔴'}


def month_bounds(value):
    start = value.replace(day=1)
    last = calendar.monthrange(start.year, start.month)[1]
    return start.isoformat(), start.replace(day=last).isoformat()


def month_entries(client, params):
    """Загружаем весь выбранный месяц, а не только первую страницу календаря."""
    result, page = [], 1
    while True:
        response = client.call('schedule', params={**params, 'page': page,
                               'page_size': 100, 'sort_by': 'PlannedAt', 'sort_dir': 'asc'})
        batch = response.get('items', [])
        result.extend(batch)
        if not batch or len(result) >= response.get('total', len(result)):
            return result
        page += 1


def calendar_view(client, lookups, filters=None, key='schedule-calendar'):
    filters = filters or {}
    st.subheader('Календарь технического обслуживания')
    default = date.fromisoformat(str(filters.get('from') or utc_now().date())[:10])
    controls = st.columns([2, 2, 1])
    with controls[0]:
        month = st.date_input('Любая дата нужного месяца', value=default,
                              key=key + ':month', format='DD.MM.YYYY')
    with controls[1]:
        status = st.selectbox('Статус в календаре', ['Все'] + STATUSES,
                              key=key + ':status')
    with controls[2]:
        only_overdue = st.checkbox('Просроченные', key=key + ':overdue')
    start, finish = month_bounds(month)
    params = {name: value for name, value in filters.items()
              if name in ('workshop_id', 'workshop_ids', 'equipment_id', 'priority', 'type')
              and value is not None}
    params.update({'from': start, 'to': finish})
    if status not in ('Все', 'просрочено'):
        params['status'] = status
    if only_overdue or status == 'просрочено':
        params['overdue'] = 'true'
    try:
        rows = month_entries(client, params)
    except ApiError as error:
        error_message(error)
        return
    st.caption(f'ТО за выбранный месяц: {len(rows)}. Даты и время — UTC. '
               '🔴 просрочено · 🟢 выполнено · ⚪ отменено. Нажмите событие для карточки.')
    by_day = {}
    for row in rows:
        by_day.setdefault(str(row['PlannedAt'])[:10], []).append(row)
    for column, name in zip(st.columns(7), ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']):
        column.markdown('**' + name + '**')
    equipment = choices(lookups, 'equipment')
    for week in calendar.Calendar().monthdatescalendar(month.year, month.month):
        for column, day in zip(st.columns(7), week):
            with column, st.container(border=True):
                if day.month != month.month:
                    st.caption(str(day.day))
                    continue
                st.markdown(f'**{day.day}**')
                for row in by_day.get(day.isoformat(), []):
                    state = 'просрочено' if row.get('IsOverdue') else row['Status']
                    name = row.get('EquipmentName') or equipment.get(row['EquipmentId'], 'ТО')
                    label = f"{ICONS.get(state, '🔵')} {name}"
                    help_text = f"{row.get('MaintenanceTypeName', 'ТО')}: {row['PlannedAt']} · {state}"
                    if st.button(label, key=f"{key}:event:{row['Id']}",
                                 help=help_text, width='stretch'):
                        navigate('schedule', row['Id'])


def render(client, lookups):
    calendar_view(client, lookups, st.session_state.get('route_filters'), key='schedule')


def render_order(client, row, lookups):
    if client.user.get('Role') not in ('admin', 'engineer', 'master'):
        return
    if row['Status'] in ('выполнено', 'отменено'):
        return
    equipment = next((item for item in lookups.get('equipment', [])
                      if item['id'] == row['EquipmentId']), {})
    workshop = equipment.get('workshop_id')
    masters = {item['id']: item['label'] for item in lookups.get('masters', [])
               if item.get('workshop_id') == workshop}
    if client.user.get('Role') == 'master':
        masters = {ident: name for ident, name in masters.items() if ident == client.user['Id']}
    if not masters:
        st.warning('В цехе оборудования нет доступного активного мастера. '
                   'Проверьте справочник пользователей.')
        return
    key = f"schedule:{row['Id']}:order"
    planned = datetime.fromisoformat(str(row['PlannedAt']).replace('Z', '+00:00'))
    planned = planned.replace(tzinfo=None)
    overdue = planned < utc_now()
    initial = utc_now() + timedelta(hours=1) if overdue else planned
    with st.expander('Создать заявку по этому ТО'):
        if overdue:
            st.warning('Плановая дата прошла: укажите новое начало в будущем (UTC).')
        st.caption('Повторное создание откроет уже связанную заявку. '
                   'Норматив длительности и пересечение занятости проверяет сервер.')
        with st.form(key):
            default_master = client.user.get('Id') if client.user.get('Id') in masters else None
            master = lookup_input('Ответственный мастер *', masters, key + ':master',
                                  value=default_master, optional=False)
            start = st.text_input('Плановое начало UTC *', initial.isoformat(timespec='seconds'),
                                  key=key + ':start')
            hours = st.text_input('Длительность в часах (пусто — норматив)', key=key + ':hours')
            team = lookup_input('Бригада', choices(lookups, 'teams'), key + ':team',
                                value=row.get('TeamId'))
            priority = st.selectbox('Приоритет', ['низкий', 'средний', 'высокий', 'критический'],
                                    index=1, key=key + ':priority')
            submitted = st.form_submit_button('Создать / открыть заявку', type='primary')
        if not submitted:
            return
        payload = {'master_id': master, 'planned_start': start.strip(),
                   'priority': priority, 'team_id': team}
        if not start.strip():
            st.error('Укажите плановое начало в UTC.')
            return
        if hours.strip():
            payload['planned_hours'] = hours.strip()
        try:
            order = client.call(f"schedule/{row['Id']}/create-order", method='POST',
                                payload=payload, action=key)
            st.session_state['notice'] = ('Открыта существующая заявка.' if order.get('ScheduleOrderReused')
                                          else 'Плановая заявка создана.')
            navigate('work-orders', order['Id'])
        except ApiError as error:
            error_message(error)
