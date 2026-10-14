"""Общие элементы интерфейса; соединений с SQL Server здесь нет."""
import csv
import io
from datetime import datetime, timezone

import streamlit as st

from api_client import ApiError

ROLE_NAMES = {
    'admin': 'Администратор', 'engineer': 'Инженер ТОиР',
    'master': 'Мастер цеха', 'member': 'Член бригады',
    'manager': 'Руководитель',
}


def error_message(error):
    st.error(getattr(error, 'message', str(error)))
    if getattr(error, 'status', None) == 409:
        st.info('Обновите карточку перед повтором: данные могли измениться.')


def fetch(client, path, params=None, default=None):
    try:
        return client.call(path, params=params)
    except ApiError as error:
        error_message(error)
        return default


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def fmt(value, digits=2):
    if value is None:
        return '—'
    if isinstance(value, (int, float)):
        formatted = f'{value:,.{digits}f}'.replace(',', ' ')
        return formatted.rstrip('0').rstrip('.') if digits else formatted
    return str(value)


def display_name(row):
    return str(row.get('DisplayNumber') or row.get('Name') or row.get('label')
               or row.get('Number') or row.get('Email') or f"#{row.get('Id')}")


def choices(lookups, resource):
    return {row['id']: row['label'] for row in lookups.get(resource, [])}


def lookup_input(label, entries, key, value=None, optional=True, disabled=False):
    values = list(entries)
    if optional:
        values.insert(0, None)
    if value is not None and value not in values:
        values.append(value)
    if not values:
        values = [None]
    index = values.index(value) if value in values else 0
    return st.selectbox(
        label, values, index=index, key=key, disabled=disabled,
        format_func=lambda item: entries.get(item, f'#{item}') if item else 'Не выбрано',
    )


def csv_bytes(rows, columns):
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter=';')
    writer.writerow(columns.values())
    for row in rows:
        cells = []
        for name in columns:
            value = row.get('DisplayNumber', row.get(name)) if name == 'Number' else row.get(name)
            if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r')):
                value = "'" + value
            cells.append(value)
        writer.writerow(cells)
    return ('\ufeff' + output.getvalue()).encode('utf-8')


def table(rows, columns, key, target=None):
    if not rows:
        st.info('По выбранным условиям данных нет.')
        return
    search = st.text_input('Поиск в таблице', key=f'{key}:search')
    filtered = [row for row in rows if search.casefold() in str(row).casefold()]
    visible = [{label: row.get('DisplayNumber', row.get(name)) if name == 'Number'
                else row.get(name) for name, label in columns.items()} for row in filtered]
    selected = st.dataframe(
        visible, hide_index=True, width='stretch', key=f'{key}:table',
        on_select='rerun' if target else 'ignore', selection_mode='single-row',
    )
    st.download_button('CSV таблицы', csv_bytes(filtered, columns), f'{key}.csv',
                       'text/csv', key=f'{key}:csv', on_click='ignore')
    if target and selected.selection.rows:
        row = filtered[selected.selection.rows[0]]
        if st.button('Открыть выбранную запись', key=f'{key}:open'):
            target(row)


def navigate(page, ident=None, filters=None):
    st.session_state['pending_page'] = page
    st.session_state['selected_record'] = {'resource': page, 'id': ident}
    st.session_state['route_filters'] = filters or {}
    st.session_state.pop('editor', None)
    st.rerun()


def success(message):
    st.session_state['notice'] = message
    st.rerun()


def export_control(client, report_type, params, key, block=None):
    slot = f'export:{key}'
    if st.button('Подготовить PDF', key=f'{key}:prepare'):
        payload = {**params, 'type': report_type, 'format': 'pdf'}
        if block:
            payload['block'] = block
        if report_type == 'analytics' and params.get('type'):
            payload['order_type'] = params['type']
        try:
            response = client.call('reports/export', method='POST', payload=payload,
                                   action=f'{key}:export')
            st.session_state[slot] = client.download(response['url'])
        except ApiError as error:
            error_message(error)
    if slot in st.session_state:
        st.download_button('Скачать PDF', st.session_state[slot], f'{key}.pdf',
                           'application/pdf', key=f'{key}:download', on_click='ignore')
