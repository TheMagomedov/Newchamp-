"""Реестры: один шаблон списка, фильтров, импорта и редактирования."""
from math import ceil

import streamlit as st

from api_client import ApiError
from common import choices, csv_bytes, error_message, fetch, lookup_input, navigate, success
from details import display_value, render_detail
from forms import begin_edit, render_form

PREFERRED = {
    'equipment': ['InventoryNumber', 'Name', 'Model', 'WorkshopId', 'Status'],
    'work-orders': ['Number', 'EquipmentId', 'Type', 'Priority', 'Status', 'PlannedEnd'],
    'schedule': ['EquipmentId', 'MaintenanceTypeId', 'PlannedAt', 'TeamId', 'Status'],
    'materials': ['Code', 'Name', 'Unit', 'Stock', 'MinimumStock', 'UnitPrice'],
    'teams': ['Code', 'Name', 'Specialization', 'WorkshopId', 'IsActive'],
    'users': ['LastName', 'FirstName', 'Email', 'RoleId', 'IsActive'],
}


def filters_panel(resource, lookups):
    key = resource['key']
    slot = 'filters:' + key
    incoming = st.session_state.pop('route_filters', {})
    if incoming:
        st.session_state[slot] = incoming
        st.session_state['filter-revision:' + key] = st.session_state.get('filter-revision:' + key, 0) + 1
    applied = st.session_state.setdefault(slot, {})
    revision = st.session_state.get('filter-revision:' + key, 0)
    prefix = f'filters:{key}:{revision}:'
    fields = {field['name']: field for field in resource['fields']}
    with st.expander('Поиск и фильтры', expanded=True):
        with st.form(prefix + 'form'):
            values = {'search': st.text_input('Поиск по реестру', applied.get('search', ''),
                                              max_chars=150, key=prefix + 'search')}
            columns = st.columns(2)
            with columns[0]:
                if 'Status' in fields:
                    options = fields['Status'].get('options') or []
                    values['status'] = lookup_input('Статус', {v: v for v in options},
                                                   prefix + 'status', applied.get('status'))
                if key in ('equipment', 'work-orders', 'schedule', 'teams'):
                    shops = choices(lookups, 'workshops')
                    selected = str(applied.get('workshop_ids', applied.get('workshop_id', ''))).split(',')
                    initial = [ident for ident in shops if str(ident) in selected]
                    selected = st.multiselect('Цеха', list(shops), initial,
                                              format_func=shops.get, key=prefix + 'shops')
                    values['workshop_ids'] = ','.join(map(str, selected))
            with columns[1]:
                if key in ('work-orders', 'schedule'):
                    values['equipment_id'] = lookup_input('Оборудование', choices(lookups, 'equipment'),
                                                          prefix + 'equipment', applied.get('equipment_id'))
                    values['team_id'] = lookup_input('Бригада', choices(lookups, 'teams'),
                                                     prefix + 'team', applied.get('team_id'))
                if key == 'work-orders':
                    for param, field in [('priority', 'Priority'), ('type', 'Type')]:
                        options = fields[field].get('options') or []
                        values[param] = lookup_input(fields[field]['label'], {v: v for v in options},
                                                      prefix + param, applied.get(param))
            if key in ('equipment', 'work-orders', 'schedule'):
                columns = st.columns(2)
                values['from'] = columns[0].text_input('Дата с (YYYY-MM-DD, UTC)', applied.get('from', ''), key=prefix + 'from')
                values['to'] = columns[1].text_input('Дата по (YYYY-MM-DD, UTC)', applied.get('to', ''), key=prefix + 'to')
                if key == 'equipment':
                    st.caption('Период относится к дате добавления оборудования.')
            if key == 'schedule':
                values['overdue'] = st.checkbox('Только просроченное ТО', bool(applied.get('overdue')), key=prefix + 'overdue')
            submitted = st.form_submit_button('Применить', type='primary')
        if submitted:
            st.session_state[slot] = {name: value for name, value in values.items() if value not in ('', None, False)}
            st.session_state['page:' + key] = 1
            st.rerun()
        if st.button('Сбросить фильтры', key=prefix + 'reset'):
            st.session_state[slot] = {}
            st.session_state['page:' + key] = 1
            st.session_state['filter-revision:' + key] = revision + 1
            st.rerun()
    return dict(applied)


def equipment_import(client, resource):
    if resource['key'] != 'equipment' or client.user.get('Role') not in ('admin', 'engineer'):
        return
    with st.expander('Импорт оборудования из CSV / XLSX'):
        st.caption('Максимум 2 МБ, UTF-8 для CSV. Заголовки — имена полей API; внешние ключи — ID.')
        columns = {field['name']: field['name'] for field in resource['fields']
                   if field.get('required') and not field.get('readOnly')}
        st.download_button('Шаблон CSV (заголовки)', csv_bytes([], columns), 'equipment-template.csv',
                           'text/csv', key='import-template', on_click='ignore')
        st.caption('Обязательные столбцы: ' + ', '.join(columns) + '. '
                   'Остальные поля можно добавить по именам API. Пример даты: 2027-03-01.')
        with st.form('equipment-import'):
            upload = st.file_uploader('Файл оборудования', type=['csv', 'xlsx'], key='equipment-upload')
            confirmed = st.checkbox('Проверил файл; добавить все его строки в БД', key='equipment-import-confirm')
            submitted = st.form_submit_button('Импортировать')
        if submitted:
            if not upload or not confirmed:
                st.warning('Выберите файл и подтвердите импорт.')
            elif upload.size > 2 * 1024 * 1024:
                st.error('Файл больше 2 МБ.')
            else:
                try:
                    result = client.call('import/equipment', method='POST', raw=upload.getvalue(),
                                         params={'filename': upload.name}, action='equipment-import')
                    success(f"Импортировано записей: {result['inserted']}.")
                except ApiError as error:
                    error_message(error)


def render(client, resource, lookups):
    key = resource['key']
    st.header(resource['label'])
    if render_form(client, resource, lookups):
        return
    selected = st.session_state.get('selected_record') or {}
    if selected.get('resource') == key and selected.get('id'):
        row = fetch(client, f"{key}/{selected['id']}")
        if row:
            render_detail(client, resource, row, lookups)
        elif st.button('Вернуться к списку', key='missing-detail-back'):
            navigate(key)
        return
    if resource.get('canWrite') and st.button('Добавить запись', key='add:' + key, type='primary'):
        begin_edit(resource)
    equipment_import(client, resource)
    params = filters_panel(resource, lookups)
    fields = {field['name']: field for field in resource['fields'] if field['type'] != 'password'}
    names = PREFERRED.get(key, [name for name in fields if name not in ('Id', 'Version')][:6])
    shown = [fields[name] for name in names if name in fields]
    columns = st.columns([2, 1, 1])
    sorting = {name: field['label'] for name, field in fields.items() if name != 'Version'}
    sort = columns[0].selectbox('Сортировать по', list(sorting), format_func=sorting.get, key='sort:' + key)
    direction = columns[1].selectbox('Порядок', ['desc', 'asc'],
                                     format_func=lambda value: 'Убывание' if value == 'desc' else 'Возрастание', key='direction:' + key)
    size = columns[2].selectbox('На странице', [25, 50, 100], key='size:' + key)
    page_slot = 'page:' + key
    page = st.session_state.setdefault(page_slot, 1)
    data = fetch(client, key, {**params, 'page': page, 'page_size': size, 'sort_by': sort, 'sort_dir': direction})
    if data is None:
        return
    total, rows = data['total'], data['items']
    pages = max(1, ceil(total / size))
    if page > pages:
        st.session_state[page_slot] = pages
        st.rerun()
    st.caption(f'Записей: {total}. Страница {page} из {pages}. Выберите строку, затем откройте карточку.')
    if rows:
        visible = [{field['label']: display_value(row, field, lookups) for field in shown} for row in rows]
        selection_key = f"list:{key}:{page}:{hash(str(visible))}"
        result = st.dataframe(visible, hide_index=True, width='stretch', key=selection_key,
                              on_select='rerun', selection_mode='single-row')
        if result.selection.rows and st.button('Открыть карточку', key='open:' + key):
            navigate(key, rows[result.selection.rows[0]]['Id'])
        labeled = {field['name']: field['label'] for field in shown}
        exported = [{field['name']: display_value(row, field, lookups) for field in shown} for row in rows]
        st.download_button('CSV текущей страницы', csv_bytes(exported, labeled), f'{key}.csv',
                           'text/csv', key='list-csv:' + key, on_click='ignore')
    else:
        st.info('Записей нет. Попробуйте изменить фильтры.')
    previous, refresh, following = st.columns(3)
    if previous.button('← Назад', disabled=page <= 1, key='previous:' + key):
        st.session_state[page_slot] -= 1
        st.rerun()
    if refresh.button('Обновить', key='refresh-list:' + key):
        st.rerun()
    if following.button('Далее →', disabled=page >= pages, key='next:' + key):
        st.session_state[page_slot] += 1
        st.rerun()
