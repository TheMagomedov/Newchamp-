"""Предпросмотр и выгрузка. Временную ссылку скачиваем сразу через API."""
from datetime import timedelta

import streamlit as st

from api_client import ApiError
from charts import chart
from common import choices, error_message, table, utc_now

TYPES = {
    'equipment': 'Реестр оборудования', 'work-orders': 'Реестр заявок',
    'materials': 'Склад материалов', 'downtime': 'Простои оборудования',
    'schedule': 'Выполнение графика ТО', 'team-efficiency': 'Эффективность бригад',
    'material-usage': 'Расход материалов', 'analytics': 'Вся аналитика',
}
MIMES = {'pdf': 'application/pdf', 'csv': 'text/csv',
         'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}


def render(client, lookups):
    st.header('Отчёты и экспорт')
    today = utc_now().date()
    with st.form('reports-form'):
        report_type = st.selectbox('Вид отчёта', list(TYPES), format_func=TYPES.get)
        left, right = st.columns(2)
        start = left.date_input('С', today - timedelta(days=29))
        end = right.date_input('По', today)
        shops = choices(lookups, 'workshops')
        selected = st.multiselect('Цеха', list(shops), format_func=shops.get)
        file_format = st.selectbox('Формат выгрузки', ['pdf', 'xlsx', 'csv'])
        preview = st.form_submit_button('Предпросмотр', type='primary')
        export = st.form_submit_button('Подготовить файл')
    if preview or export:
        if start > end:
            st.error('Начало периода не может быть позже окончания.')
        else:
            params = {'type': report_type, 'from': start.isoformat(), 'to': end.isoformat()}
            if selected:
                params['workshop_ids'] = ','.join(map(str, selected))
            try:
                st.session_state['report_preview'] = client.call('reports/preview', params=params)
                st.session_state['report_period'] = (start.isoformat(), end.isoformat())
                st.session_state.pop('report_file', None)
                if export:
                    result = client.call('reports/export', method='POST',
                                         payload={**params, 'format': file_format}, action='report-export')
                    data = client.download(result['url'])
                    st.session_state['report_file'] = (data, result.get('filename', f'report.{file_format}'),
                                                       MIMES[file_format])
            except ApiError as error:
                error_message(error)
    if 'report_file' in st.session_state:
        data, filename, mime = st.session_state['report_file']
        st.download_button('Скачать готовый файл', data, filename, mime, on_click='ignore')
    result = st.session_state.get('report_preview')
    if result:
        st.subheader(result['title'])
        st.caption('Период: ' + ' — '.join(st.session_state['report_period']))
        columns = {item['key']: item['label'] for item in result['columns']}
        table(result['rows'], columns, 'report-preview')
        for index, item in enumerate(result.get('charts') or []):
            chart(item['title'], item['items'], f'report-chart-{index}', kind=item.get('mode', 'bar'))
    st.caption('PDF/XLSX/CSV формирует сервер. Файлы хранятся только в текущем сеансе веба.')
