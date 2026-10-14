"""Пять аналитических блоков; значения полностью приходят из API."""
import streamlit as st

from charts import chart
from common import export_control, navigate, table
from schedule import calendar_view


def render_sections(client, data, filters, lookups):
    st.subheader('1. Объём и структура заявок')
    left, right = st.columns(2)
    with left:
        chart('По типам', data.get('orders_by_type', []), 'orders-types', kind='pie',
              target=lambda row: navigate('work-orders', filters={**filters, 'type': row['label']}))
    with right:
        chart('По приоритетам', data.get('orders_by_priority', []), 'orders-priority', kind='pie',
              target=lambda row: navigate('work-orders', filters={**filters, 'priority': row['label']}))
    table(data.get('orders_by_status', []), {'label': 'Статус', 'value': 'Количество'},
          'orders-status', target=lambda row: navigate('work-orders',
          filters={**filters, 'status': row['label']}))
    export_control(client, 'analytics', filters, 'orders-block', 'orders')

    st.subheader('2. Анализ простоев')
    st.caption('Графики динамики показывают последние 30 дней выбранного периода.')
    chart('Динамика простоев, ч', data.get('downtime_daily', []), 'downtime-daily',
          label='date', value='hours', kind='line')
    table(data.get('top_downtime', []), {'label': 'Оборудование', 'inventory_number': 'Инв. номер',
          'hours': 'Простой, ч'}, 'downtime-details',
          target=lambda row: navigate('equipment', row['equipment_id']))
    export_control(client, 'analytics', filters, 'downtime-block', 'downtime')

    st.subheader('3. Расход материалов')
    chart('Топ-10 материалов по стоимости', data.get('materials_top', []), 'materials-top',
          value='cost', target=lambda row: navigate('materials', row['material_id']))
    table(data.get('materials_daily', []), {'date': 'Дата', 'cost': 'Стоимость, ₽'},
          'materials-daily')
    table(data.get('materials_all', data.get('materials_top', [])),
          {'label': 'Материал', 'quantity': 'Количество', 'unit': 'Единица', 'cost': 'Стоимость, ₽'},
          'materials-usage', target=lambda row: navigate('materials', row['material_id']))
    export_control(client, 'analytics', filters, 'materials-block', 'materials')

    st.subheader('4. Выполнение графика ТО')
    schedule = data.get('schedule', {})
    table(schedule.get('by_workshop', []), {'label': 'Цех', 'planned': 'План',
          'completed': 'Факт', 'on_time': 'В срок', 'overdue': 'Просрочено',
          'adherence_percent': 'Выполнение, %'}, 'maintenance-plan',
          target=lambda row: navigate('schedule', filters={**filters,
          'workshop_ids': str(row['workshop_id'])}))
    chart('Выполнение ТО по цехам, %', schedule.get('by_workshop', []), 'maintenance-shops',
          value='adherence_percent')
    calendar_view(client, lookups, filters, key='analytics-calendar')
    export_control(client, 'analytics', filters, 'maintenance-block', 'schedule')

    st.subheader('5. Эффективность бригад')
    rows = [dict(row, rank=index + 1) for index, row in enumerate(data.get('team_rankings', []))]
    chart('Выполненные работы по бригадам', rows, 'teams-comparison', value='completed',
          target=lambda row: navigate('teams', row['team_id']))
    table(rows, {'rank': 'Место', 'label': 'Бригада', 'completed': 'Выполнено',
          'active': 'Активно', 'avg_completion_hours': 'Среднее, ч', 'on_time_percent': 'В срок, %'},
          'team-rankings', target=lambda row: navigate('teams', row['team_id']))
    export_control(client, 'analytics', filters, 'teams-block', 'teams')
