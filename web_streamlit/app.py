"""Вход и навигация. Все данные приходят из FastAPI, не из SQL напрямую."""
import os
import time

import streamlit as st

from api_client import ApiClient, ApiError
from common import ROLE_NAMES, error_message
import dashboard
import reports
import resources_view
import schedule
import search

st.set_page_config(page_title='ТОиР-Проф · Python', page_icon='⚙️', layout='wide')
st.markdown('''<style>
    [data-testid="stMetric"] {padding:18px;border-radius:12px;
        border:1px solid #dce6e8;}
    .stMainBlockContainer {padding-top:2rem;}
</style>''', unsafe_allow_html=True)

LABELS = {
    'dashboard': 'Обзор предприятия', 'analytics': 'Аналитика',
    'work-orders': 'Заявки', 'equipment': 'Оборудование', 'schedule': 'График ТО',
    'directories': 'Справочники', 'reports': 'Отчёты',
    'search': 'Поиск', 'notifications': 'Уведомления', 'users': 'Пользователи',
}


def login(client):
    st.title('ТОиР-Проф')
    st.caption('Оборудование, обслуживание и материалы · веб на Python')
    with st.form('login-form'):
        email = st.text_input('Электронная почта', value='admin@toir.local', key='login-email')
        password = st.text_input('Пароль', type='password', key='login-password')
        submitted = st.form_submit_button('Войти', type='primary')
    if submitted:
        try:
            client.login(email, password)
            st.session_state.clear()
            st.session_state['api_client'] = client
            st.rerun()
        except ApiError as error:
            error_message(error)
    st.caption('Запустите API в другом терминале. Адрес задаётся через start_streamlit.ps1.')


def context(client):
    if time.monotonic() - st.session_state.get('context_at', 0) > 30:
        metadata = client.call('meta')
        lookups = client.call('lookups')
        st.session_state['context'] = (metadata, lookups)
        st.session_state['context_at'] = time.monotonic()
    return st.session_state['context']


def workspace(client):
    metadata, lookups = context(client)
    resources = {item['key']: item for item in metadata['resources']}
    options = [key for key in LABELS if key != 'users' or 'users' in resources]
    pending = st.session_state.pop('pending_page', None)
    if pending:
        if pending in options:
            st.session_state['page'] = pending
        elif pending in resources:
            st.session_state['page'] = 'directories'
            st.session_state['directory_key'] = pending
    if st.session_state.get('page') not in options:
        st.session_state['page'] = 'dashboard'
    with st.sidebar:
        st.title('⚙️ ТОиР-Проф')
        st.caption('PYTHON · STREAMLIT')
        page = st.radio('Раздел', options, format_func=LABELS.get, key='page')
        st.divider()
        st.write(client.user.get('Name', client.user.get('Email', 'Пользователь')))
        st.caption(ROLE_NAMES.get(client.user.get('Role'), 'Пользователь'))
        st.caption('Время операций: UTC. Доступ проверяет сервер.')
        if st.button('Обновить справочники', key='refresh-context'):
            st.session_state.pop('context_at', None)
            st.rerun()
        if st.button('Выйти', key='logout'):
            try:
                client.logout()
            except ApiError:
                pass
            st.session_state.clear()
            st.rerun()
    if 'notice' in st.session_state:
        st.success(st.session_state.pop('notice'))
    if page in ('dashboard', 'analytics'):
        dashboard.render(client, lookups, analytics=page == 'analytics')
    elif page == 'reports':
        reports.render(client, lookups)
    elif page == 'search':
        search.render(client)
    elif page == 'notifications':
        search.notifications(client)
    else:
        resource = page
        if page == 'directories':
            choices = [key for key in resources if key not in ('equipment', 'work-orders', 'schedule', 'users')]
            resource = st.selectbox('Справочник', choices, key='directory_key',
                                    format_func=lambda key: resources[key]['label'])
        if resource not in resources:
            st.warning('Раздел недоступен для текущей роли.')
            return
        if page == 'schedule':
            schedule.render(client, lookups)
        resources_view.render(client, resources[resource], lookups)


client = st.session_state.setdefault('api_client', ApiClient(
    os.getenv('TOIR_API_URL', 'http://127.0.0.1:8000')))
if not client.authenticated:
    login(client)
else:
    try:
        workspace(client)
    except ApiError as error:
        error_message(error)
        if not client.authenticated:
            st.rerun()
        if st.button('Повторить загрузку'):
            st.rerun()
