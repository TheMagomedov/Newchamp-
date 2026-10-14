"""Данные AppTest: ни HTTP, ни SQL, все изменения только в памяти теста."""
from copy import deepcopy
from datetime import date

from streamlit.testing.v1 import AppTest

from api_client import ApiError

LABELS = {
    'equipment': 'Оборудование', 'work-orders': 'Заявки', 'schedule': 'График ТО',
    'materials': 'Материалы', 'teams': 'Бригады', 'maintenance-types': 'Виды ТО',
    'workshops': 'Цеха', 'suppliers': 'Поставщики',
    'equipment-types': 'Типы оборудования', 'users': 'Пользователи',
}


def field(name, label, kind='text', **options):
    return dict(name=name, label=label, type=kind, required=False, readOnly=False, **options)


def resources(role):
    result = []
    for key, label in LABELS.items():
        if key == 'users' and role != 'admin':
            continue
        fields = [field('Id', 'ID', 'number'), field('Name', 'Наименование')]
        fields[0]['readOnly'] = True
        fields[1]['required'] = True
        if key == 'equipment':
            fields += [field('Status', 'Статус', 'select', options=['в работе', 'в ремонте']),
                       field('WorkshopId', 'Цех', 'select', lookup='workshops')]
        if key == 'work-orders':
            fields += [field('Priority', 'Приоритет', 'select', options=['средний', 'высокий']),
                       field('Type', 'Тип заявки', 'select', options=['текущая', 'плановая']),
                       field('Status', 'Статус', 'select', options=['создана', 'в работе'])]
        if key == 'materials':
            fields += [field('Stock', 'Остаток', 'number')]
        writable = role == 'admin' or role in ('engineer', 'master') and key != 'users'
        result.append(dict(key=key, label=label, fields=fields,
                           canWrite=writable, canDelete=writable))
    return {'resources': result, 'statuses': {
        'equipment': ['в работе', 'в ремонте'], 'work-orders': ['создана', 'в работе'],
        'schedule': ['запланировано', 'выполнено'],
    }}


def record(resource, ident=1):
    return {
        'Id': ident, 'Name': LABELS.get(resource, resource) + ' тест',
        'DisplayNumber': 'Z-2026-0001', 'Number': 'Z-2026-1', 'Status': {
            'equipment': 'в работе', 'work-orders': 'в работе',
            'schedule': 'запланировано',
        }.get(resource, ''), 'EquipmentId': 1, 'EquipmentName': 'Станок тест',
        'InventoryNumber': 'EQ-001', 'WorkshopId': 1, 'WorkshopName': 'Цех тест',
        'MasterId': 1, 'MasterName': 'Мастер тест', 'TeamId': 1, 'TeamName': 'Бригада тест',
        'MaintenanceTypeId': 1, 'MaintenanceTypeName': 'Осмотр', 'Priority': 'средний',
        'Type': 'текущая', 'PlannedAt': date.today().isoformat() + 'T08:00:00',
        'PlannedStart': '2027-03-01T08:00:00', 'PlannedEnd': '2027-03-01T09:00:00',
        'ActualStart': '2026-10-01T08:00:00', 'ActualEnd': None,
        'IsOverdue': False, 'IsActive': True, 'Stock': 5, 'MinimumStock': 1,
        'Unit': 'шт', 'UnitPrice': 10, 'Code': 'M-001', 'Version': '000001',
        'history': [], 'orders': [], 'schedule': [], 'materials': [],
        'members': [], 'active_orders': [], 'workload': {'active': 0, 'planned_hours': 0},
    }


def dashboard():
    point = {'label': 'в работе', 'value': 1}
    day = {'date': date.today().isoformat(), 'created': 1, 'completed': 0, 'hours': 2, 'cost': 10}
    return {
        'metrics': {'equipment': 1, 'open_orders': 1, 'completed_orders': 0,
                    'downtime_hours': 2, 'avg_completion_hours': None},
        'schedule': {'adherence_percent': None, 'by_workshop': []},
        'equipment_status': [point], 'orders_by_status': [point],
        'orders_by_type': [dict(point, label='текущая')],
        'orders_by_priority': [dict(point, label='средний')],
        'orders_by_workshop': [dict(point, workshop_id=1, label='Цех тест')],
        'orders_daily': [day], 'downtime_daily': [day], 'materials_daily': [day],
        'top_downtime': [{'equipment_id': 1, 'label': 'Станок тест', 'hours': 2}],
        'materials_top': [{'material_id': 1, 'label': 'Материал тест', 'cost': 10}],
        'team_rankings': [{'team_id': 1, 'label': 'Бригада тест', 'completed': 0, 'active': 1}],
        'recent_orders': [record('work-orders')],
    }


class MockApiClient:
    def __init__(self, base_url='http://test.local', role='admin', authenticated=True):
        self.base_url = base_url
        self.authenticated = authenticated
        self.user = {'Id': 1, 'Name': 'Тестовый пользователь', 'Role': role,
                     'WorkshopId': 1, 'TeamId': 1, 'Email': role + '@test.local'}
        self.calls = []
        self.denied = set()
        self.empty = False
        self.rows = {key: [record(key)] for key in LABELS}

    @property
    def mutations(self):
        return [call for call in self.calls if call['method'] != 'GET']

    def login(self, email, password):
        self.calls.append(dict(path='auth/login', method='POST', payload={'email': email}))
        if password != 'test-password':
            raise ApiError('Неверная почта или пароль.', 401)
        self.authenticated = True
        return self.user

    def logout(self):
        self.calls.append(dict(path='auth/logout', method='POST'))
        self.authenticated = False

    def call(self, path, method='GET', payload=None, params=None, **kwargs):
        self.calls.append(dict(path=path, method=method, payload=deepcopy(payload), params=params))
        if path in self.denied:
            raise ApiError('Доступ запрещён для проверки.', 403)
        if method != 'GET':
            if path == 'reports/export':
                return {'url': '/api/download/test.pdf'}
            return dict(record(path.split('/')[0]), **(payload or {}))
        if path == 'meta':
            return resources(self.user['Role'])
        if path == 'lookups':
            return {key: [{'id': 1, 'label': label + ' тест', 'workshop_id': 1}]
                    for key, label in (LABELS | {'masters': 'Мастер', 'roles': 'Роль'}).items()}
        if path == 'auth/me':
            return self.user
        if path == 'analytics/dashboard':
            return {} if self.empty else dashboard()
        if path in ('search', 'notifications'):
            return {'items': [], 'total': 0}
        if path == 'reports/preview':
            return {'type': 'equipment', 'title': 'Тестовый отчёт',
                    'columns': [{'key': 'Name', 'label': 'Наименование'}],
                    'rows': [{'Name': 'Станок тест'}], 'summary': {}, 'charts': []}
        if path.startswith('files'):
            return {'items': [], 'total': 0}
        resource, *suffix = path.split('/')
        if resource in self.rows:
            if suffix and suffix[-1] in ('history', 'materials'):
                return []
            if suffix and suffix[-1] == 'related':
                return {'orders': [], 'schedule': [], 'history': []}
            if suffix and suffix[0].isdigit():
                return record(resource, int(suffix[0]))
            return {'items': deepcopy(self.rows[resource]), 'total': len(self.rows[resource]),
                    'page': (params or {}).get('page', 1), 'page_size': 25}
        raise AssertionError('Незапланированный путь Mock API: ' + path)

    def download(self, url):
        self.calls.append(dict(path=url, method='GET'))
        return b'%PDF-test-only'


def form_app(resource='equipment', editing=False):
    app = AppTest.from_string('''
import streamlit as st
from forms import render_form
render_form(st.session_state['api_client'], st.session_state['resource'], {})
''')
    client = MockApiClient()
    meta = next(item for item in resources('admin')['resources'] if item['key'] == resource)
    app.session_state['api_client'] = client
    app.session_state['resource'] = meta
    app.session_state['editor'] = {
        'resource': resource, 'record': record(resource) if editing else {},
        'nonce': 'test-form-', 'errors': {},
    }
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app, client
