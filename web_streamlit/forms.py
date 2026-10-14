"""Формы из метаданных: снимок редактирования сохраняет исходную Version."""
from datetime import date, timedelta
from math import isfinite
from uuid import uuid4

import streamlit as st

from api_client import ApiError
from common import choices, error_message, lookup_input, success


def begin_edit(resource, record=None):
    st.session_state['editor'] = {
        'resource': resource['key'], 'record': dict(record or {}),
        'nonce': str(uuid4()), 'errors': {},
    }
    st.rerun()


def default_values(resource, user):
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    status = {'equipment': 'в работе', 'work-orders': 'создана',
              'schedule': 'запланировано'}.get(resource)
    return {
        'IsActive': True, 'RequiresStop': True, 'Priority': 'средний',
        'Type': 'текущая', 'Status': status, 'Stock': 0, 'MinimumStock': 0,
        'IntervalKind': 'days', 'CommissionedOn': today, 'StartedOn': today,
        'PlannedStart': tomorrow + 'T08:00:00', 'PlannedEnd': tomorrow + 'T09:00:00',
        'PlannedAt': tomorrow + 'T08:00:00', 'WorkshopId': user.get('WorkshopId'),
        'MasterId': user.get('Id') if user.get('Role') == 'master' else None,
    }


def field_input(field, value, lookups, key):
    label = field['label'] + (' *' if field.get('required') else '')
    kind = field.get('type', 'text')
    if kind == 'bool':
        return st.checkbox(label, value=bool(value), key=key)
    if field.get('lookup'):
        return lookup_input(label, choices(lookups, field['lookup']), key, value)
    if field.get('options'):
        options = {}
        for item in field['options']:
            if isinstance(item, dict):
                options[item['value']] = item['label']
            else:
                options[item] = {'days': 'Календарные дни', 'hours': 'Моточасы',
                                 'condition': 'По состоянию'}.get(item, item)
        return lookup_input(label, options, key, value)
    if kind == 'textarea':
        return st.text_area(label, value=str(value or ''), key=key)
    if kind == 'number':
        return st.text_input(label, value='' if value is None else str(value), key=key,
                             help='Число. Для десятичной части используйте точку.')
    help_text = None
    if kind == 'datetime':
        help_text = 'UTC, формат 2027-03-01T08:00:00. Пусто — не указано.'
    if kind == 'date':
        help_text = 'Формат YYYY-MM-DD, например 2027-03-01.'
    return st.text_input(label, value='' if value is None else str(value), key=key,
                         type='password' if kind == 'password' else 'default',
                         help=help_text)


def render_form(client, resource, lookups):
    editor = st.session_state.get('editor')
    if not editor or editor['resource'] != resource['key']:
        return False
    if not resource.get('canWrite'):
        st.session_state.pop('editor', None)
        st.error('Нет прав на редактирование этого раздела.')
        return False
    record = editor['record']
    editing = bool(record.get('Id'))
    st.subheader('Редактирование записи' if editing else 'Новая запись')
    st.caption('Обязательные поля отмечены *. Дата и время — UTC.')
    defaults = record if editing else default_values(resource['key'], client.user)
    fields = [field for field in resource['fields'] if not field.get('readOnly')]
    if editing and resource['key'] == 'work-orders':
        fields = [field for field in fields if field['name'] != 'Status']
    values = {}
    with st.form('resource-form:' + editor['nonce']):
        for field in fields:
            name = field['name']
            value = '' if field['type'] == 'password' else defaults.get(name)
            values[name] = field_input(field, value, lookups, editor['nonce'] + name)
            if name in editor['errors']:
                st.error(editor['errors'][name])
        saved = st.form_submit_button('Сохранить запись', type='primary')
    if st.button('Отмена', key='cancel:' + editor['nonce']):
        st.session_state.pop('editor', None)
        st.rerun()
    if not saved:
        return True
    body, errors = {}, {}
    for field in fields:
        name, value = field['name'], values[field['name']]
        if field['type'] == 'password' and not value and editing:
            continue
        if value in ('', None):
            if field.get('required') or (field['type'] == 'password' and not editing):
                errors[name] = 'Заполните обязательное поле.'
            elif editing:
                body[name] = None
            continue
        try:
            body[name] = float(value) if field['type'] == 'number' else value
            if field['type'] == 'number' and not isfinite(body[name]):
                raise ValueError('non-finite number')
        except ValueError:
            errors[name] = 'Введите корректное число.'
    if errors:
        editor['errors'] = errors
        st.rerun()
    if editing and record.get('Version'):
        body['_version'] = record['Version']
    path = resource['key'] + (f"/{record['Id']}" if editing else '')
    try:
        client.call(path, method='PUT' if editing else 'POST', payload=body,
                    action='form:' + editor['nonce'])
        st.session_state.pop('editor', None)
        success('Запись сохранена.')
    except ApiError as error:
        editor['errors'] = {field['name']: error.message for field in fields
                            if field['name'] in error.message or field['label'] in error.message}
        error_message(error)
    return True
