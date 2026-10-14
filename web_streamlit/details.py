"""Карточки, связанные записи и история; изменения выполняет только API."""
import streamlit as st

from api_client import ApiError
from common import choices, display_name, error_message, fmt, navigate, success, table
from forms import begin_edit


def display_value(row, field, lookups):
    name = field['name']
    value = row.get('DisplayNumber', row.get(name)) if name == 'Number' else row.get(name)
    if value is None or value == '':
        return '—'
    if field.get('lookup'):
        return choices(lookups, field['lookup']).get(value, f'#{value}')
    if field.get('type') == 'bool':
        return 'Да' if value else 'Нет'
    if field.get('type') == 'number':
        return fmt(value, 3)
    if field.get('type') in ('date', 'datetime'):
        return str(value).replace('T', ' ') + (' UTC' if field['type'] == 'datetime' else '')
    if field.get('options'):
        for option in field['options']:
            if isinstance(option, dict) and option['value'] == value:
                return option['label']
        return {'days': 'Календарные дни', 'hours': 'Моточасы', 'condition': 'По состоянию'}.get(value, value)
    return str(value)


def history(rows, lookups, prefix):
    st.subheader('История изменения статусов')
    users = choices(lookups, 'users')
    visible = [{**row, 'Actor': users.get(row.get('ChangedBy'), f"#{row.get('ChangedBy')}")
                if row.get('ChangedBy') else 'Система'} for row in rows]
    table(visible, {'ChangedAt': 'Дата UTC', 'OldStatus': 'Было', 'NewStatus': 'Стало',
                    'Actor': 'Пользователь'}, prefix + ':history')


def links(rows, kind, title, prefix):
    st.subheader(title)
    columns = ({'Number': 'Номер', 'Status': 'Статус', 'CreatedAt': 'Создано UTC'}
               if kind == 'work-orders' else {'PlannedAt': 'Дата ТО UTC',
                                             'MaintenanceTypeName': 'Вид ТО', 'Status': 'Статус'})
    table(rows, columns, prefix, lambda row: navigate(kind, row['Id']))


def delete_control(client, resource, row):
    if not resource.get('canDelete'):
        return
    key = resource['key']
    with st.expander('Удалить / деактивировать запись'):
        st.warning(f"Выбрана запись: {display_name(row)} (ID {row['Id']}).")
        st.caption('Пользователь будет деактивирован, оборудование скрыто с сохранением истории. '
                   'Другие записи удаляются, если это разрешают связи и правила сервера.')
        with st.form(f"delete:{key}:{row['Id']}"):
            confirmed = st.checkbox('Подтверждаю удаление именно этой записи')
            submitted = st.form_submit_button('Удалить / деактивировать')
        if submitted and not confirmed:
            st.warning('Сначала подтвердите действие.')
        elif submitted:
            try:
                client.call(f"{key}/{row['Id']}", method='DELETE', action=f"delete:{key}:{row['Id']}")
                st.session_state.pop('selected_record', None)
                success('Запись удалена или деактивирована.')
            except ApiError as error:
                error_message(error)


def render_detail(client, resource, row, lookups):
    key = resource['key']
    prefix = f"detail:{key}:{row['Id']}"
    actions = st.columns(3)
    if actions[0].button('← К списку', key=prefix + ':back'):
        navigate(key)
    if actions[1].button('Обновить карточку', key=prefix + ':refresh'):
        st.rerun()
    if resource.get('canWrite') and actions[2].button('Редактировать', key=prefix + ':edit'):
        begin_edit(resource, row)
    st.subheader(display_name(row))
    if row.get('Status'):
        st.info('Статус: ' + row['Status'])
    fields = [field for field in resource['fields'] if field['type'] != 'password'
              and field['name'] != 'Version' and row.get(field['name']) is not None]
    st.dataframe([{'Поле': field['label'], 'Значение': display_value(row, field, lookups)}
                  for field in fields], hide_index=True, width='stretch')
    if key in ('equipment', 'work-orders'):
        with st.expander('История', expanded=False):
            history(row.get('history', []), lookups, prefix)
    if key == 'equipment':
        with st.expander('Связанные заявки и обслуживание', expanded=True):
            links(row.get('orders', []), 'work-orders', 'Заявки оборудования', prefix + ':orders')
            links(row.get('schedule', []), 'schedule', 'График обслуживания', prefix + ':schedule')
    elif key == 'teams':
        workload = row.get('workload', {})
        first, second = st.columns(2)
        first.metric('Активные заявки', workload.get('active', 0))
        second.metric('Плановая загрузка, ч', fmt(workload.get('planned_hours', 0)))
        table(row.get('members', []), {'LastName': 'Фамилия', 'FirstName': 'Имя',
              'Patronymic': 'Отчество', 'Email': 'Email', 'Phone': 'Телефон',
              'IsActive': 'Активен'}, prefix + ':members')
        links(row.get('active_orders', []), 'work-orders', 'Активные заявки бригады', prefix + ':active')
    elif key == 'work-orders':
        from work_orders import render
        render(client, row, lookups)
    elif key == 'schedule':
        from schedule import render_order
        render_order(client, row, lookups)
    delete_control(client, resource, row)
