"""Нативные интерактивные диаграммы Vega-Lite на данных REST API."""
from collections.abc import Mapping

import streamlit as st

from common import csv_bytes


def selection_index(point, count):
    """Vega возвращает либо список строк, либо столбцы вида {'_row': [0]}."""
    if isinstance(point, Mapping):
        values = point.get('_row', [])
        values = values if isinstance(values, list) else [values]
    elif isinstance(point, list):
        values = [row.get('_row') for row in point if isinstance(row, Mapping)]
    else:
        return None
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if isinstance(value, float) and not value.is_integer():
            continue
        if 0 <= value < count:
            return int(value)
    return None


def chart(title, rows, key, label='label', value='value', kind='bar', target=None):
    st.markdown(f'#### {title}')
    data = [{**row, '_row': index} for index, row in enumerate(rows)
            if row.get(value) is not None]
    if not data:
        st.info('Нет данных для диаграммы.')
        return
    encoding = {
        'tooltip': [{'field': label, 'type': 'nominal', 'title': 'Показатель'},
                    {'field': value, 'type': 'quantitative', 'title': 'Значение'}],
    }
    if kind == 'pie':
        encoding.update(theta={'field': value, 'type': 'quantitative'},
                        color={'field': label, 'type': 'nominal', 'title': None})
        mark = {'type': 'arc', 'innerRadius': 65}
    elif kind == 'line':
        encoding.update(x={'field': label, 'type': 'temporal', 'title': 'Дата'},
                        y={'field': value, 'type': 'quantitative', 'title': None})
        mark = {'type': 'line', 'point': True, 'color': '#178478'}
    else:
        encoding.update(x={'field': value, 'type': 'quantitative', 'title': None},
                        y={'field': label, 'type': 'nominal', 'sort': '-x', 'title': None})
        mark = {'type': 'bar', 'color': '#178478', 'cornerRadiusEnd': 4}
    specification = {'mark': mark, 'encoding': encoding, 'height': 260}
    if target:
        specification['params'] = [{'name': 'point', 'select': {'type': 'point',
                                     'fields': ['_row']}}]
    result = st.vega_lite_chart(
        data, specification, width='stretch', key=f'{key}:chart',
        on_select='rerun' if target else 'ignore',
    )
    if target:
        selection = result.get('selection', {})
        selected = selection_index(selection.get('point'), len(rows)) if isinstance(selection, Mapping) else None
        if selected is not None and st.button('Открыть выбранное значение', key=f'{key}:open'):
            target(rows[selected])
    st.download_button('CSV диаграммы', csv_bytes(rows, {label: 'Показатель', value: 'Значение'}),
                       f'{key}.csv', 'text/csv', key=f'{key}:csv', on_click='ignore')
