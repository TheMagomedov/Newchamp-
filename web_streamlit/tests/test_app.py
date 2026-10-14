"""AppTest проверяет настоящий UI с API-двойником; никаких записей в SQL."""
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from fixtures import LABELS, MockApiClient, form_app

APP = Path(__file__).resolve().parents[1] / 'app.py'


def button(app, label):
    return next(item for item in app.button if item.label == label)


def clean(app):
    assert not app.exception, [item.message for item in app.exception]


def opened(role='admin', page='dashboard', selected=None):
    client = MockApiClient(role=role)
    app = AppTest.from_file(APP, default_timeout=20)
    app.session_state['api_client'] = client
    app.session_state['pending_page'] = page
    if selected:
        app.session_state['selected_record'] = {'resource': page, 'id': selected}
    app.run()
    clean(app)
    return app, client


@pytest.mark.parametrize('page', ['dashboard', 'analytics', *LABELS, 'directories', 'reports', 'search', 'notifications'])
def test_all_pages_render_without_implicit_writes(page):
    app, client = opened(page=page)
    assert app.header or app.title
    assert not client.mutations


@pytest.mark.parametrize('page', ['equipment', 'work-orders', 'schedule', 'teams', 'materials'])
def test_cards_render_without_implicit_writes(page):
    _, client = opened(page=page, selected=1)
    assert any(item['path'] == f'{page}/1' for item in client.calls)
    assert not client.mutations


@pytest.mark.parametrize('page', ['equipment', 'work-orders', 'schedule', 'materials'])
def test_manager_sees_data_but_no_mutation_controls(page):
    app, client = opened(role='manager', page=page, selected=1)
    labels = [item.label for item in app.button if not item.disabled]
    forbidden = ('Создать', 'Сохранить', 'Удалить', 'Редактировать', 'Списать', 'Добавить', 'Изменить статус')
    assert not any(label.startswith(forbidden) for label in labels)
    assert not client.mutations


def test_dashboard_shows_six_metrics_and_no_fake_missing_average():
    app, _ = opened()
    assert len(app.metric) == 6
    assert any(item.label == 'Среднее время, ч' and item.value == '—' for item in app.metric)
    assert len(app.get('vega_lite_chart')) == 4


def test_api_denial_becomes_message_not_stacktrace():
    client = MockApiClient()
    client.denied.add('analytics/dashboard')
    app = AppTest.from_file(APP, default_timeout=20)
    app.session_state['api_client'] = client
    app.run()
    clean(app)
    assert any('Доступ запрещён' in item.value for item in app.error)
    assert not client.mutations


def test_login_waits_for_submit_and_rejects_invalid_credentials():
    client = MockApiClient(authenticated=False)
    app = AppTest.from_file(APP, default_timeout=20)
    app.session_state['api_client'] = client
    app.run()
    clean(app)
    assert not client.calls
    app.text_input(key='login-password').set_value('wrong').run()
    assert not client.calls
    button(app, 'Войти').click().run()
    clean(app)
    assert any('Неверная почта' in item.value for item in app.error)
    assert not client.authenticated
    assert len(client.mutations) == 1


def test_successful_login_clears_stale_user_state_and_password():
    client = MockApiClient(authenticated=False)
    app = AppTest.from_file(APP, default_timeout=20)
    app.session_state['api_client'] = client
    app.session_state['search_results'] = [{'label': 'Данные другого пользователя'}]
    app.run()
    app.text_input(key='login-password').set_value('test-password')
    button(app, 'Войти').click().run()
    clean(app)
    assert client.authenticated
    assert 'search_results' not in app.session_state
    assert 'login-password' not in app.session_state
    assert len(app.metric) == 6


def test_logout_clears_identity_and_per_user_cache():
    app, client = opened()
    app.session_state['filter_templates'] = {'private': {'workshop_ids': '1'}}
    app.button(key='logout').click().run()
    clean(app)
    assert not client.authenticated
    assert 'filter_templates' not in app.session_state
    assert not app.radio
    assert app.text_input(key='login-password').value == ''
    assert [call['path'] for call in client.mutations] == ['auth/logout']


def test_manager_cannot_navigate_to_users_page():
    app, client = opened(role='manager', page='users')
    assert 'Пользователи' not in app.radio(key='page').options
    assert not any(call['path'].startswith('users') for call in client.calls)


@pytest.mark.parametrize('page', ['dashboard', 'analytics', 'equipment', 'schedule', 'notifications'])
def test_empty_responses_render_clear_states_without_exception(page):
    client = MockApiClient()
    client.empty = True
    client.rows = {key: [] for key in LABELS}
    app = AppTest.from_file(APP, default_timeout=20)
    app.session_state['api_client'] = client
    app.session_state['pending_page'] = page
    app.run()
    clean(app)
    assert app.info or app.success or app.metric
    assert not client.mutations


def test_report_preview_and_export_are_separate_explicit_actions():
    app, client = opened(page='reports')
    button(app, 'Предпросмотр').click().run()
    clean(app)
    assert any(item.value == 'Тестовый отчёт' for item in app.subheader)
    assert not client.mutations
    button(app, 'Подготовить файл').click().run()
    clean(app)
    assert len(client.mutations) == 1
    assert client.mutations[0]['path'] == 'reports/export'
    assert app.session_state['report_file'][0] == b'%PDF-test-only'
    app.run()
    assert len(client.mutations) == 1


def test_filter_template_updates_both_applied_filter_and_visible_widgets():
    app, client = opened()
    app.session_state['filter_templates'] = {'Март': {'from': '2027-03-01', 'to': '2027-03-31',
                                                     'workshop_ids': '1', 'priority': 'высокий'}}
    app.run()
    button(app, 'Загрузить шаблон').click().run()
    clean(app)
    assert app.date_input(key='analytics-from').value == date(2027, 3, 1)
    assert app.date_input(key='analytics-to').value == date(2027, 3, 31)
    assert app.multiselect(key='analytics-workshops').value == [1]
    assert app.selectbox(key='analytics-priority').value == 'высокий'
    assert app.session_state['analytics_filters']['from'] == '2027-03-01'
    button(app, 'Сбросить фильтры').click().run()
    clean(app)
    assert app.multiselect(key='analytics-workshops').value == []
    assert app.selectbox(key='analytics-priority').value == ''
    assert not client.mutations


def test_form_open_and_widget_change_never_save_without_submit():
    app, client = form_app()
    app.text_input(key='test-form-Name').set_value('Новое имя').run()
    clean(app)
    assert not client.mutations


def test_missing_required_field_is_not_sent_to_api():
    app, client = form_app()
    button(app, 'Сохранить запись').click().run()
    clean(app)
    assert any('Заполните обязательное поле' in item.value for item in app.error)
    assert not client.mutations


def test_explicit_create_submits_exactly_once():
    app, client = form_app()
    app.text_input(key='test-form-Name').set_value('Новый станок')
    button(app, 'Сохранить запись').click().run()
    clean(app)
    assert len(client.mutations) == 1
    assert client.mutations[0]['method'] == 'POST'
    assert client.mutations[0]['payload']['Name'] == 'Новый станок'
    app.run()
    assert len(client.mutations) == 1


def test_edit_preserves_version_and_uses_put():
    app, client = form_app(editing=True)
    app.text_input(key='test-form-Name').set_value('Исправленный станок')
    button(app, 'Сохранить запись').click().run()
    clean(app)
    assert len(client.mutations) == 1
    assert client.mutations[0]['method'] == 'PUT'
    assert client.mutations[0]['path'] == 'equipment/1'
    assert client.mutations[0]['payload']['_version'] == '000001'


def test_bad_number_is_local_error_and_preserves_input():
    app, client = form_app(resource='materials', editing=True)
    app.text_input(key='test-form-Stock').set_value('не число')
    button(app, 'Сохранить запись').click().run()
    clean(app)
    assert any('Введите корректное число' in item.value for item in app.error)
    assert app.text_input(key='test-form-Stock').value == 'не число'
    assert not client.mutations


def test_cancel_edit_never_writes():
    app, client = form_app(editing=True)
    button(app, 'Отмена').click().run()
    clean(app)
    assert 'editor' not in app.session_state
    assert not client.mutations


def test_delete_requires_explicit_confirmation():
    app, client = opened(page='equipment', selected=1)
    button(app, 'Удалить / деактивировать').click().run()
    clean(app)
    assert any('Сначала подтвердите' in item.value for item in app.warning)
    assert not client.mutations


def test_atomic_completion_requires_report_and_sends_one_request():
    app, client = opened(page='work-orders', selected=1)
    button(app, 'Сохранить отчёт и завершить').click().run()
    clean(app)
    assert not client.mutations
    app.text_area(key='order:1:complete:report').set_value('Работы выполнены')
    button(app, 'Сохранить отчёт и завершить').click().run()
    clean(app)
    assert len(client.mutations) == 1
    assert client.mutations[0]['path'] == 'work-orders/1/complete'
    assert client.mutations[0]['payload']['completion_report'] == 'Работы выполнены'
