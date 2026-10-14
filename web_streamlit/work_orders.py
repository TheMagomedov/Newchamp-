"""Фрагмент: жизненный цикл заявки, склад и атомарное завершение через API."""
import streamlit as st

from api_client import ApiError
from common import choices, error_message, lookup_input, success, table

TRANSITIONS = {
    'создана': ['назначена', 'отменена'],
    'назначена': ['в работе', 'создана', 'отменена'],
    'в работе': ['ожидает материалов'],
    'ожидает материалов': ['в работе'],
    'выполнена': ['закрыта'],
}
WRITERS = {'admin', 'engineer', 'master', 'member'}
STOCK_WRITERS = {'admin', 'master', 'member'}


def available_transitions(status, role):
    """Клиент помогает выбрать действие; окончательные правила проверяет сервер."""
    if role not in WRITERS:
        return []
    targets = TRANSITIONS.get(status, [])
    if role == 'member':
        return [item for item in targets if item in ('в работе', 'ожидает материалов')]
    return targets


def mutate(client, path, payload, action, message, method='POST'):
    try:
        client.call(path, method=method, payload=payload, action=action)
        success(message)
    except ApiError as error:
        error_message(error)


def transition_controls(client, row, lookups):
    ident, status = row['Id'], row['Status']
    targets = available_transitions(status, client.user.get('Role'))
    if not targets:
        return
    key = f'order:{ident}:transition:{status}'
    target = st.selectbox('Следующий статус', targets, key=key + ':status')
    with st.form(key + ':' + target):
        payload = {'status': target}
        if target == 'назначена':
            payload['team_id'] = lookup_input(
                'Бригада *', choices(lookups, 'teams'), key + ':team', row.get('TeamId'))
        if target == 'в работе' and not row.get('ActualStart'):
            start = st.text_input('Фактическое начало UTC (пусто — сейчас)',
                                  key=key + ':start', placeholder='2027-03-10T08:00:00')
            if start.strip():
                payload['actual_start'] = start.strip()
        confirmed = True
        if target in ('отменена', 'закрыта'):
            confirmed = st.checkbox('Подтверждаю изменение статуса', key=key + ':confirm')
        submitted = st.form_submit_button('Изменить статус', type='primary')
    if submitted:
        if not confirmed:
            st.warning('Подтвердите действие.')
        elif target == 'назначена' and not payload['team_id']:
            st.error('Выберите бригаду для назначения.')
        else:
            mutate(client, f'work-orders/{ident}/transition', payload, key,
                   'Статус заявки изменён.')


def material_controls(client, row, lookups, lines):
    ident = row['Id']
    if client.user.get('Role') not in STOCK_WRITERS:
        st.caption('Списывать материалы могут администратор, мастер и участник бригады.')
        return
    if row['Status'] in ('закрыта', 'отменена'):
        return
    key = f'order:{ident}:materials'
    used = {item['MaterialId']: item for item in lines}
    operations = ['Добавить'] + (['Изменить', 'Удалить'] if used else [])
    operation = st.radio('Действие с материалом', operations, horizontal=True,
                         key=key + ':operation')
    labels = choices(lookups, 'materials')
    entries = {ident: name for ident, name in labels.items() if ident not in used}
    if operation != 'Добавить':
        entries = {ident: line.get('MaterialName', labels.get(ident, f'#{ident}'))
                   for ident, line in used.items()}
    if not entries:
        st.info('Нет новых материалов для списания. Существующие строки можно изменить.')
        return
    material = lookup_input('Материал', entries, key + ':' + operation, optional=False)
    selected = used.get(material, {})
    form_key = f'{key}:{operation}:{material}'
    with st.form(form_key):
        if operation == 'Удалить':
            st.caption('Удаление списания возвращает количество на склад.')
            confirmed = st.checkbox('Подтверждаю удаление списания', key=form_key + ':confirm')
            payload = {}
        else:
            quantity = st.number_input('Количество *', min_value=0.001, step=0.1,
                                       value=float(selected.get('Quantity', 1)),
                                       format='%.3f', key=form_key + ':quantity')
            comment = st.text_input('Комментарий', value=selected.get('Comment') or '',
                                    key=form_key + ':comment')
            payload = {'Quantity': quantity, 'Comment': comment}
            confirmed = True
        submitted = st.form_submit_button(operation + ' материал')
    if not submitted:
        return
    if not confirmed:
        st.warning('Подтвердите удаление.')
        return
    path = f'work-orders/{ident}/materials'
    if operation == 'Добавить':
        payload['MaterialId'] = material
        method = 'POST'
    else:
        path += f'/{material}'
        method = 'DELETE' if operation == 'Удалить' else 'PUT'
    mutate(client, path, payload, form_key, 'Материалы заявки обновлены.', method)


def completion_controls(client, row, lookups, lines):
    if row['Status'] != 'в работе' or client.user.get('Role') not in WRITERS:
        return
    key = f"order:{row['Id']}:complete"
    with st.expander('Завершить работу: отчёт и материалы одной операцией'):
        st.caption('Отчёт, новые списания и статус сохраняются одной транзакцией. '
                   'При нехватке материала изменения не применяются.')
        used = {line['MaterialId'] for line in lines}
        available = {ident: name for ident, name in choices(lookups, 'materials').items()
                     if ident not in used}
        selected = []
        if client.user.get('Role') in STOCK_WRITERS:
            previous = st.session_state.get(key + ':selected', [])
            if any(ident not in available for ident in previous):
                st.session_state[key + ':selected'] = [ident for ident in previous if ident in available]
            selected = st.multiselect('Дополнительно списать при завершении',
                                      list(available), format_func=available.get,
                                      key=key + ':selected')
            st.caption('Уже списанные материалы изменяются отдельной формой выше.')
        with st.form(key):
            report = st.text_area('Отчёт о выполненных работах *', key=key + ':report')
            actual_end = st.text_input('Фактическое окончание UTC (пусто — сейчас)',
                                       key=key + ':end', placeholder='2027-03-10T09:00:00')
            materials = []
            for ident in selected:
                quantity = st.number_input(f'Количество: {available[ident]}',
                                           min_value=0.001, value=1.0, step=0.1,
                                           format='%.3f', key=f'{key}:quantity:{ident}')
                materials.append({'MaterialId': ident, 'Quantity': quantity})
            submitted = st.form_submit_button('Сохранить отчёт и завершить', type='primary')
        if submitted:
            if not report.strip():
                st.error('Введите отчёт о выполненных работах.')
                return
            payload = {'completion_report': report.strip(), 'materials': materials}
            if actual_end.strip():
                payload['actual_end'] = actual_end.strip()
            mutate(client, f"work-orders/{row['Id']}/complete", payload, key,
                   'Работа завершена. Отчёт и материалы сохранены.')


def render(client, row, lookups):
    st.subheader('Выполнение заявки')
    st.write('Текущий статус:', row.get('Status', '—'))
    st.caption('Даты вводятся в UTC. Пустое фактическое время сервер заменяет текущим.')
    transition_controls(client, row, lookups)
    st.subheader('Материалы заявки')
    lines = row.get('materials', [])
    table(lines, {'MaterialName': 'Материал', 'Unit': 'Ед.', 'Quantity': 'Количество',
                  'UnitPrice': 'Цена при списании', 'Comment': 'Комментарий'},
          key=f"order:{row['Id']}:material-table")
    material_controls(client, row, lookups, lines)
    completion_controls(client, row, lookups, lines)
