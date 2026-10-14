"""Поиск и уведомления в доступной пользователю области."""
import streamlit as st

from common import fetch, navigate


def render(client):
    st.header('Глобальный поиск')
    with st.form('search-form'):
        query = st.text_input('Номер заявки, оборудование, материал или ФИО', key='search-query')
        submitted = st.form_submit_button('Найти', type='primary')
    if submitted:
        st.session_state['search_results'] = fetch(client, 'search', {'q': query, 'limit': 50},
                                                   default={'items': []})['items']
    for index, row in enumerate(st.session_state.get('search_results', [])):
        with st.container(border=True):
            st.write(row['label'])
            st.caption(row.get('subtitle', ''))
            if st.button('Открыть', key=f'search-open:{index}'):
                navigate(row['resource'], row['id'])
    if submitted and not st.session_state.get('search_results'):
        st.info('Ничего не найдено. Попробуйте другой запрос.')


def notifications(client):
    st.header('Уведомления')
    st.button('Обновить уведомления')
    data = fetch(client, 'notifications', default={'items': []})
    read = st.session_state.setdefault('read_notifications', set())
    unread = sum(row['id'] not in read for row in data['items'])
    st.caption(f'Непрочитанных: {unread}. Отметки сохраняются только в этом сеансе.')
    if not data['items']:
        st.success('Текущих уведомлений нет.')
    for row in data['items']:
        with st.container(border=True):
            st.markdown('**' + row['title'] + '**')
            st.write(row['message'])
            left, right = st.columns(2)
            if left.button('Открыть запись', key=f"notification-open:{row['id']}"):
                navigate(row['resource'], row['entity_id'])
            if right.button('Прочитано', key=f"notification-read:{row['id']}", disabled=row['id'] in read):
                read.add(row['id'])
                st.rerun()
