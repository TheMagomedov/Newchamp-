<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import Icon from './Icon.vue';
import DataTable from './DataTable.vue';
import MaintenanceCalendar from './MaintenanceCalendar.vue';
import { fieldErrors } from './data.js';
import { transitionPayload } from './transitions.js';
import { request, query, createMutationAttempt } from './api.js';
import { number, date, badge, readable, utcInput } from './format.js';
const props = defineProps({ resource: Object, lookups: Object, user: Object, initialFilters: { default: () => ({}) }, initialId: [String, Number] });
const emit = defineEmits(['changed', 'notify', 'navigate']);
const items = ref([]); const total = ref(0); const page = ref(1); const pageSize = ref(25);
const sortBy = ref(''); const sortDirection = ref('asc');
const search = ref(props.initialFilters.search || ''); const status = ref(props.initialFilters.status || ''); const workshop = ref(props.initialFilters.workshop_id || ''); const loading = ref(false); const error = ref('');
const priority = ref(props.initialFilters.priority || ''); const orderType = ref(props.initialFilters.type || '');
const dateFrom = ref(props.initialFilters.from || ''); const dateTo = ref(props.initialFilters.to || '');
const equipmentFilter = ref(props.initialFilters.equipment_id || ''); const workshopsFilter = ref(props.initialFilters.workshop_ids || '');
const related = ref({ orders: [], schedule: [] }); const errors = ref({}); const drawerRoot = ref(null);
const calendarRevision = ref(0); const orderMaster = ref(props.user?.Role === 'master' ? props.user.Id : '');
const scheduleStart = ref(''); const scheduleHours = ref('');
const masterOptions = computed(() => {
  const workshopId = selected.value?.WorkshopId || props.lookups.equipment?.find(x => String(x.id) === String(selected.value?.EquipmentId))?.workshop_id;
  return (props.lookups.masters || []).filter(person => !workshopId || !person.workshop_id || Number(person.workshop_id) === Number(workshopId));
});
let previousFocus; let revisionTimer; let detailRequestId = 0;
const drawer = ref(null); const selected = ref(null); const form = ref({}); const busy = ref(false); const formError = ref(''); const detailsLoading = ref(false);
const history = ref([]); const materials = ref([]); const deleteTarget = ref(null); const deleteError = ref('');
const transition = ref({ status: '', team_id: '', actual_start: '', actual_end: '', completion_report: '' });
const materialForm = ref({ MaterialId: '', Quantity: 1, Comment: '' }); const detailTab = ref('info');
const importInput = ref(null); const importing = ref(false); const importResult = ref('');
let searchTimer; let requestId = 0;
const saveAttempt = createMutationAttempt(); const deleteAttempt = createMutationAttempt();
const transitionAttempt = createMutationAttempt(); const materialAddAttempt = createMutationAttempt();
const materialEditAttempt = createMutationAttempt(); const materialDeleteAttempt = createMutationAttempt();
const importAttempt = createMutationAttempt();
const scheduleAttempt = createMutationAttempt();
function resetDrawerAttempts() { errors.value = {}; for (const attempt of [saveAttempt, transitionAttempt, materialAddAttempt, materialEditAttempt, materialDeleteAttempt, scheduleAttempt]) attempt.reset(); }
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
const statuses = computed(() => props.resource.fields.find(x => x.name === 'Status')?.options || []);
const editable = computed(() => props.resource.fields.filter(x => !x.readOnly && !(selected.value && props.resource.key === 'work-orders' && x.name === 'Status')));
const columns = computed(() => {
  const preferred = {
    equipment: ['InventoryNumber', 'Name', 'Model', 'WorkshopId', 'Status'],
    'work-orders': ['Number', 'EquipmentId', 'Type', 'Priority', 'Status', 'PlannedEnd'],
    schedule: ['EquipmentId', 'MaintenanceTypeId', 'PlannedAt', 'TeamId', 'Status'],
    materials: ['Code', 'Name', 'Unit', 'Stock', 'MinimumStock', 'UnitPrice'],
    teams: ['Code', 'Name', 'Specialization', 'WorkshopId', 'IsActive'],
    users: ['LastName', 'FirstName', 'Email', 'RoleId', 'IsActive'],
    'maintenance-types': ['Code', 'Name', 'IntervalKind', 'IntervalDays', 'PlannedHours', 'IsActive'],
  }[props.resource.key];
  return preferred ? preferred.map(name => props.resource.fields.find(x => x.name === name)).filter(Boolean) : props.resource.fields.filter(x => !['Id', 'Version'].includes(x.name) && x.type !== 'password').slice(0, 6);
});
const infoFields = computed(() => props.resource.fields.filter(x => x.type !== 'password' && x.name !== 'Version' && selected.value?.[x.name] != null));
const canTransition = computed(() => props.resource.key === 'work-orders' && ['admin', 'master', 'engineer', 'member'].includes(props.user?.Role));
const canMaterials = computed(() => props.resource.key === 'work-orders' && ['admin', 'master', 'member'].includes(props.user?.Role) && !['закрыта', 'отменена'].includes(selected.value?.Status));
const allowedTransitions = computed(() => {
  const transitions = ({ 'создана': ['назначена', 'отменена'], 'назначена': ['в работе', 'отменена'], 'в работе': ['ожидает материалов', 'выполнена'], 'ожидает материалов': ['в работе'], 'выполнена': ['закрыта'], 'закрыта': [], 'отменена': [] })[selected.value?.Status] || [];
  return props.user?.Role === 'member' ? transitions.filter(x => ['в работе', 'ожидает материалов', 'выполнена'].includes(x)) : transitions;
});
const totalMaterialCost = computed(() => materials.value.reduce((s, x) => s + Number(x.Quantity || 0) * Number(x.UnitPrice || 0), 0));
const subtitle = computed(() => ({ equipment: 'Единый реестр производственного оборудования.', 'work-orders': 'Планируйте, назначайте и контролируйте ремонтные работы.', schedule: 'Плановое обслуживание и назначение ответственных бригад.', users: 'Учётные записи и разграничение прав доступа.' })[props.resource.key] || 'Актуальные данные для ежедневной работы службы ТОиР.');
function options(field) { return field.lookup ? (props.lookups[field.name === 'MasterId' ? 'masters' : field.lookup] || []).map(x => ({ value: x.id, label: x.label })) : (field.options || []).map(x => typeof x === 'object' ? x : ({ value: x, label: ({ days: 'Календарные дни', hours: 'Моточасы', condition: 'По состоянию' })[x] || x })); }
function display(value, field) {
  if (value == null || value === '') return '—';
  if (field?.lookup) return props.lookups[field.lookup]?.find(x => String(x.id) === String(value))?.label || `#${value}`;
  if (field?.type === 'date' || field?.type === 'datetime') return date(value);
  if (field?.type === 'bool') return value ? 'Да' : 'Нет';
  if (field?.type === 'number') return number(value, 3);
  if (field?.options) return options(field).find(x => x.value === value)?.label || value;
  return value;
}
async function load(reset = false) {
  if (reset) page.value = 1;
  const id = ++requestId; loading.value = true; error.value = '';
  try {
    const result = await request(`${props.resource.key}?${query({ search: search.value, status: status.value, page: page.value, page_size: pageSize.value, workshop_id: workshop.value, workshop_ids: workshop.value ? '' : workshopsFilter.value, equipment_id: equipmentFilter.value, priority: priority.value, type: orderType.value, from: dateFrom.value, to: dateTo.value, sort_by: sortBy.value, sort_dir: sortDirection.value })}`);
    if (id === requestId) { items.value = result.items || []; total.value = result.total || 0; }
  } catch (e) { if (id === requestId) error.value = e.message; }
  finally { if (id === requestId) loading.value = false; }
}
function searchChanged() { clearTimeout(searchTimer); searchTimer = setTimeout(() => load(true), 350); }
function sort(field) { sortDirection.value = sortBy.value === field && sortDirection.value === 'asc' ? 'desc' : 'asc'; sortBy.value = field; load(true); }
function openCreate() {
  detailRequestId++;
  resetDrawerAttempts();
  selected.value = null; formError.value = '';
  const day = new Date().toISOString().slice(0, 10); const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  const defaults = { IsActive: true, RequiresStop: true, Priority: 'средний', Type: 'текущая', Status: ({ equipment: 'в работе', 'work-orders': 'создана', schedule: 'запланировано' })[props.resource.key], Stock: 0, MinimumStock: 0, IntervalKind: 'days', CommissionedOn: day, StartedOn: day, PlannedStart: `${tomorrow}T08:00`, PlannedEnd: `${tomorrow}T09:00`, PlannedAt: `${tomorrow}T08:00`, MasterId: props.user?.Id, WorkshopId: props.user?.WorkshopId || '' };
  form.value = Object.fromEntries(editable.value.map(x => [x.name, defaults[x.name] ?? (x.type === 'bool' ? false : '')]));
  drawer.value = 'form';
}
function openEdit(row = selected.value) {
  detailRequestId++;
  resetDrawerAttempts();
  selected.value = { ...row }; formError.value = '';
  form.value = Object.fromEntries(props.resource.fields.filter(x => !x.readOnly).map(x => [x.name, x.type === 'password' ? '' : x.type === 'datetime' ? (row[x.name] || '').slice(0, 19) : row[x.name] ?? (x.type === 'bool' ? false : '')]));
  drawer.value = 'form';
}
async function openDetails(row) {
  const detailId = ++detailRequestId;
  resetDrawerAttempts();
  selected.value = row; drawer.value = 'details'; detailTab.value = 'info'; formError.value = ''; history.value = []; materials.value = []; detailsLoading.value = true;
  transition.value = { status: '', team_id: row.TeamId || '', actual_start: utcInput(), actual_end: utcInput(), completion_report: row.CompletionReport || '' };
  try {
    const record = await request(`${props.resource.key}/${row.Id}`);
    if (detailId !== detailRequestId) return;
    selected.value = record;
    if (props.resource.key === 'schedule') { scheduleStart.value = (selected.value.PlannedAt || '').slice(0, 19); scheduleHours.value = ''; }
    if (['equipment', 'work-orders'].includes(props.resource.key)) { const rows = await request(`${props.resource.key}/${row.Id}/history`); if (detailId === detailRequestId) history.value = rows; }
    if (props.resource.key === 'work-orders') { const rows = await request(`work-orders/${row.Id}/materials`); if (detailId === detailRequestId) materials.value = rows; }
    if (props.resource.key === 'equipment') { const rows = await request(`equipment/${row.Id}/related`); if (detailId === detailRequestId) related.value = rows; }
  } catch (e) { if (detailId === detailRequestId) formError.value = e.message; } finally { if (detailId === detailRequestId) detailsLoading.value = false; }
}
function closeDrawer() { if (!busy.value) { detailRequestId++; resetDrawerAttempts(); drawer.value = null; formError.value = ''; } }
async function save() {
  busy.value = true; formError.value = ''; errors.value = {};
  const body = {};
  for (const f of editable.value) {
    const value = form.value[f.name];
    if (f.type === 'password' && !value) continue;
    if ((value === '' || value == null) && !selected.value) continue;
    body[f.name] = value === '' || value == null ? null : f.type === 'number' || f.lookup ? Number(value) : value;
  }
  if (selected.value?.Version) body._version = selected.value.Version;
  try {
    await saveAttempt.run(`${props.resource.key}${selected.value ? `/${selected.value.Id}` : ''}`, { method: selected.value ? 'PUT' : 'POST', body });
    drawer.value = null; await load(); emit('changed', selected.value ? 'Запись обновлена' : 'Запись создана');
  } catch (e) { formError.value = e.message; errors.value = fieldErrors(e, editable.value); await nextTick(); drawerRoot.value?.querySelector('[aria-invalid="true"]')?.focus(); } finally { busy.value = false; }
}
function askDelete(row) { deleteAttempt.reset(); deleteTarget.value = row; deleteError.value = ''; }
async function remove() {
  busy.value = true; deleteError.value = '';
  try { await deleteAttempt.run(`${props.resource.key}/${deleteTarget.value.Id}`, { method: 'DELETE' }); deleteTarget.value = null; drawer.value = null; await load(); emit('changed', 'Запись удалена или деактивирована'); }
  catch (e) { deleteError.value = e.message; } finally { busy.value = false; }
}
async function changeStatus() {
  busy.value = true; formError.value = '';
  const body = transitionPayload(transition.value, selected.value);
  try { await transitionAttempt.run(`work-orders/${selected.value.Id}/transition`, { method: 'POST', body }); await openDetails(selected.value); await load(); emit('changed', 'Статус заявки изменён'); }
  catch (e) { formError.value = e.message; } finally { busy.value = false; }
}
async function saveMaterial() {
  busy.value = true; formError.value = '';
  try {
    await materialAddAttempt.run(`work-orders/${selected.value.Id}/materials`, { method: 'POST', body: { ...materialForm.value, MaterialId: Number(materialForm.value.MaterialId), Quantity: Number(materialForm.value.Quantity) } });
    materials.value = await request(`work-orders/${selected.value.Id}/materials`); materialForm.value = { MaterialId: '', Quantity: 1, Comment: '' }; emit('changed', 'Материал списан в заявку');
  } catch (e) { formError.value = e.message; } finally { busy.value = false; }
}
async function updateMaterial(row) {
  busy.value = true; formError.value = '';
  try { await materialEditAttempt.run(`work-orders/${selected.value.Id}/materials/${row.MaterialId}`, { method: 'PUT', body: { Quantity: Number(row._quantity), Comment: row.Comment || '' } }); materials.value = await request(`work-orders/${selected.value.Id}/materials`); emit('changed', 'Количество материала обновлено'); }
  catch (e) { formError.value = e.message; } finally { busy.value = false; }
}
async function removeMaterial(row) {
  if (!window.confirm(`Удалить «${row.MaterialName || row.MaterialId}» из заявки?`)) { materialDeleteAttempt.reset(); return; }
  busy.value = true; formError.value = '';
  try { await materialDeleteAttempt.run(`work-orders/${selected.value.Id}/materials/${row.MaterialId}`, { method: 'DELETE' }); materials.value = await request(`work-orders/${selected.value.Id}/materials`); emit('changed', 'Материал удалён из заявки'); }
  catch (e) { formError.value = e.message; } finally { busy.value = false; }
}
async function importEquipment(event) {
  const file = event.target.files?.[0]; if (!file) return;
  if (file.size > 2 * 1024 * 1024) { error.value = 'Размер файла не должен превышать 2 МБ.'; event.target.value = ''; return; }
  importing.value = true; error.value = ''; importResult.value = '';
  try { const result = await importAttempt.run(`import/equipment?filename=${encodeURIComponent(file.name)}`, { method: 'POST', raw: true, headers: { 'Content-Type': file.name.endsWith('.csv') ? 'text/csv' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }, body: file }); importResult.value = `Импортировано записей: ${result.inserted}`; await load(); emit('changed', importResult.value); }
  catch (e) { error.value = e.message; } finally { importing.value = false; event.target.value = ''; }
}
async function createScheduleOrder() {
  busy.value = true; formError.value = '';
  try {
    const body = { master_id: Number(orderMaster.value) };
    if (scheduleStart.value) body.planned_start = scheduleStart.value;
    if (scheduleHours.value !== '') body.planned_hours = Number(scheduleHours.value);
    const order = await scheduleAttempt.run(`schedule/${selected.value.Id}/create-order`, { method: 'POST', body });
    emit('changed', 'Плановая заявка создана'); emit('navigate', { page: 'work-orders', id: order.Id });
  } catch (e) { formError.value = e.message; } finally { busy.value = false; }
}
function calendarPeriod(value) { dateFrom.value = value.from; dateTo.value = value.to; load(true); }
function resetFilters() { search.value = ''; status.value = ''; workshop.value = ''; workshopsFilter.value = ''; equipmentFilter.value = ''; priority.value = ''; orderType.value = ''; dateFrom.value = ''; dateTo.value = ''; load(true); }
function refreshFromEvent() { clearTimeout(revisionTimer); revisionTimer = setTimeout(() => { load(); calendarRevision.value++; }, 300); }
function escapeKey(event) {
  if (event.key === 'Escape' && !busy.value) { deleteTarget.value = null; closeDrawer(); }
  if (event.key === 'Tab' && drawer.value && drawerRoot.value) {
    const controls = [...drawerRoot.value.querySelectorAll('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]')].filter(x => x.offsetParent !== null);
    if (!controls.length) return;
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
}
watch(drawer, async (value, before) => {
  if (value && !before) { previousFocus = document.activeElement; await nextTick(); drawerRoot.value?.querySelector('input,select,textarea,button')?.focus(); }
  if (!value) previousFocus?.focus();
});
onMounted(() => { load(); if (props.initialId) openDetails({ Id: Number(props.initialId) }); window.addEventListener('keydown', escapeKey); window.addEventListener('toir-revision', refreshFromEvent); });
onUnmounted(() => { requestId++; detailRequestId++; clearTimeout(searchTimer); clearTimeout(revisionTimer); window.removeEventListener('keydown', escapeKey); window.removeEventListener('toir-revision', refreshFromEvent); });
</script>
<template>
  <section>
    <div class="page-heading">
      <div><p class="eyebrow">{{ resource.key === 'work-orders' ? 'УПРАВЛЕНИЕ РАБОТАМИ' : resource.key === 'schedule' ? 'ПЛАНИРОВАНИЕ' : 'РЕЕСТР ДАННЫХ' }}</p><h1>{{ resource.label }}<span class="heading-count">{{ number(total) }}</span></h1><p>{{ subtitle }}</p></div>
      <div class="heading-actions">
        <template v-if="resource.key === 'equipment' && ['admin', 'engineer'].includes(user?.Role)"><input ref="importInput" type="file" accept=".csv,.xlsx" class="visually-hidden" @change="importEquipment"><button class="button" @click="importInput.click()" :disabled="importing"><Icon name="upload" :size="17"/>{{ importing ? 'Импорт…' : 'Импорт' }}</button></template>
        <button v-if="resource.canWrite" class="button primary" @click="openCreate"><Icon name="plus" :size="18"/>Добавить</button>
      </div>
    </div>
    <div v-if="importResult" class="alert success"><Icon name="check"/>{{ importResult }}</div>
    <section class="panel section-gap">
      <form class="resource-toolbar extended-toolbar" @submit.prevent="load(true)">
        <div class="search-field"><Icon name="search" :size="18"/><input v-model="search" @input="searchChanged" type="search" placeholder="Поиск по записям…" aria-label="Поиск по записям"></div>
        <label v-if="statuses.length">Статус<select v-model="status" @change="load(true)"><option value="">Все статусы</option><option v-for="option in statuses" :key="typeof option === 'object' ? option.value : option" :value="typeof option === 'object' ? option.value : option">{{ typeof option === 'object' ? option.label : option }}</option></select></label>
        <label v-if="['equipment', 'schedule', 'work-orders'].includes(resource.key)">Цех<select v-model="workshop" @change="workshopsFilter = ''; load(true)"><option value="">Все цеха</option><option v-for="x in lookups.workshops || []" :key="x.id" :value="x.id">{{ x.label }}</option></select></label>
        <template v-if="resource.key === 'work-orders'">
          <label>Тип<select v-model="orderType" @change="load(true)"><option value="">Все типы</option><option>плановая</option><option>текущая</option><option>аварийная</option></select></label>
          <label>Приоритет<select v-model="priority" @change="load(true)"><option value="">Все приоритеты</option><option>низкий</option><option>средний</option><option>высокий</option><option>критический</option></select></label>
        </template>
        <template v-if="['work-orders', 'schedule'].includes(resource.key)">
          <label>Период с<input v-model="dateFrom" type="date" :max="dateTo || undefined" @change="load(true)"></label><label>по<input v-model="dateTo" type="date" :min="dateFrom || undefined" @change="load(true)"></label>
          <label>Оборудование<select v-model="equipmentFilter" @change="load(true)"><option value="">Все единицы</option><option v-for="x in lookups.equipment || []" :key="x.id" :value="x.id">{{ x.label }}</option></select></label>
        </template>
        <button type="button" class="icon-button refresh-table" @click="load(); calendarRevision++" aria-label="Обновить список" :disabled="loading"><Icon name="refresh" :size="18" :class="{ spinning: loading }"/></button>
        <button type="button" class="text-button" @click="resetFilters">Сбросить</button>
        <small v-if="workshopsFilter" class="active-filter-note">Цеха из аналитики: {{ workshopsFilter }}</small>
      </form>
    </section>
    <MaintenanceCalendar v-if="resource.key === 'schedule'" :initial-date="initialFilters.from" :workshop="workshop" :workshops="workshopsFilter" :equipment="equipmentFilter" :status="status" :revision="calendarRevision" @period="calendarPeriod" @select="openDetails"/>
    <section class="panel table-panel resource-panel">
      <div v-if="error" class="alert error table-alert" role="alert"><Icon name="alert"/><span>{{ error }}</span><button class="text-button" @click="load()">Повторить</button></div>
      <div v-if="loading && !items.length" class="loading-panel"><span class="spinner"></span>Загружаем записи…</div>
      <div v-else class="table-scroll">
        <table><thead><tr><th class="row-number">№</th><th v-for="field in columns" :key="field.name" :aria-sort="sortBy === field.name ? sortDirection === 'asc' ? 'ascending' : 'descending' : 'none'"><button class="sort-button" @click="sort(field.name)">{{ field.label }}<span :class="{ sorted: sortBy === field.name }">{{ sortBy === field.name ? sortDirection === 'asc' ? '↑' : '↓' : '↕' }}</span></button></th><th class="actions-cell">Действия</th></tr></thead>
          <tbody><tr v-for="(row, index) in items" :key="row.Id" @dblclick="openDetails(row)">
            <td class="row-number">{{ (page - 1) * pageSize + index + 1 }}</td>
            <td v-for="(field, fieldIndex) in columns" :key="field.name" :class="{ 'strong-cell': fieldIndex === 0 }">
              <button v-if="fieldIndex === 0" class="cell-link" @click="openDetails(row)">{{ field.name === 'Number' ? row.DisplayNumber || display(row[field.name], field) : display(row[field.name], field) }}</button>
              <span v-else-if="field.name === 'Status' || field.name === 'Priority'" class="status-badge" :class="badge(row[field.name])">{{ row[field.name] }}</span>
              <span v-else-if="field.type === 'bool'" class="status-badge" :class="row[field.name] ? 'success' : 'neutral'">{{ row[field.name] ? 'Да' : 'Нет' }}</span>
              <span v-else :class="{ 'danger-text': field.name === 'Stock' && Number(row.Stock) < Number(row.MinimumStock) }">{{ display(row[field.name], field) }}</span>
            </td>
            <td class="actions-cell"><button class="icon-button" @click="openDetails(row)" title="Открыть запись" aria-label="Открыть запись"><Icon name="chevron" :size="17"/></button><button v-if="resource.canWrite" class="icon-button" @click="openEdit(row)" title="Редактировать" aria-label="Редактировать запись"><Icon name="edit" :size="17"/></button><button v-if="resource.canDelete" class="icon-button danger-hover" @click="askDelete(row)" title="Удалить / деактивировать" aria-label="Удалить или деактивировать запись"><Icon name="delete" :size="17"/></button></td>
          </tr><tr v-if="!items.length"><td :colspan="columns.length + 2" class="empty-cell"><div class="table-empty"><Icon name="search" :size="34"/><strong>Записей не найдено</strong><span>Измените фильтры или добавьте новую запись.</span><button v-if="resource.canWrite" class="button small" @click="openCreate">Добавить запись</button></div></td></tr></tbody>
        </table>
      </div>
      <div class="pagination"><span>{{ total ? `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)}` : '0' }} из {{ number(total) }} записей</span><div><label>На странице<select v-model.number="pageSize" @change="load(true)"><option :value="25">25</option><option :value="50">50</option><option :value="100">100</option></select></label><button class="icon-button previous" @click="page--; load()" :disabled="page <= 1 || loading" aria-label="Предыдущая страница"><Icon name="chevron" :size="18"/></button><span>{{ page }} / {{ pageCount }}</span><button class="icon-button" @click="page++; load()" :disabled="page >= pageCount || loading" aria-label="Следующая страница"><Icon name="chevron" :size="18"/></button></div></div>
    </section>
    <div v-if="drawer" class="drawer-backdrop" @click.self="closeDrawer">
      <section ref="drawerRoot" class="drawer" role="dialog" aria-modal="true" :aria-label="drawer === 'form' ? 'Редактирование записи' : 'Карточка записи'">
        <div class="drawer-header"><div><p class="eyebrow">{{ resource.label }}</p><h2>{{ drawer === 'form' ? selected ? 'Редактирование записи' : 'Новая запись' : selected?.DisplayNumber || selected?.Number || selected?.Name || selected?.Email || `Запись #${selected?.Id}` }}</h2></div><button class="icon-button" @click="closeDrawer" aria-label="Закрыть карточку" :disabled="busy"><Icon name="close"/></button></div>
        <div v-if="formError" class="alert error drawer-alert" role="alert"><Icon name="alert"/>{{ formError }}</div>
        <form v-if="drawer === 'form'" class="drawer-form" @submit.prevent="save">
          <div class="drawer-body"><p class="form-help">Поля со звёздочкой обязательны. Дата и время вводятся в UTC.</p>
            <div class="form-grid">
              <label v-for="field in editable" :key="field.name" :class="{ 'full-width': field.type === 'textarea', 'checkbox-field': field.type === 'bool', 'invalid-field': !!errors[field.name] }">
                <template v-if="field.type === 'bool'"><input v-model="form[field.name]" type="checkbox"><span>{{ field.label }}</span></template>
                <template v-else>
                  <span>{{ field.label }}<b v-if="field.required || (field.type === 'password' && !selected)" class="required"> *</b></span>
                  <select v-if="field.type === 'select'" v-model="form[field.name]" :required="field.required" :aria-invalid="!!errors[field.name]" :aria-describedby="errors[field.name] ? 'error-' + field.name : undefined" @change="delete errors[field.name]"><option value="">{{ field.required ? 'Выберите значение' : 'Не указано' }}</option><option v-for="option in options(field)" :key="option.value" :value="option.value">{{ option.label }}</option></select>
                  <textarea v-else-if="field.type === 'textarea'" v-model="form[field.name]" :required="field.required" rows="3" :aria-invalid="!!errors[field.name]" :aria-describedby="errors[field.name] ? 'error-' + field.name : undefined" @input="delete errors[field.name]"></textarea>
                  <input v-else v-model="form[field.name]" :type="field.type === 'datetime' ? 'datetime-local' : ['date', 'number', 'password'].includes(field.type) ? field.type : field.name === 'Email' ? 'email' : 'text'" :step="field.type === 'number' ? 'any' : field.type === 'datetime' ? 1 : undefined" :minlength="field.type === 'password' ? 8 : undefined" :required="field.required || (field.type === 'password' && !selected)" :autocomplete="field.type === 'password' ? 'new-password' : 'off'" :aria-invalid="!!errors[field.name]" :aria-describedby="errors[field.name] ? 'error-' + field.name : undefined" @input="delete errors[field.name]">
                </template>
                <small v-if="errors[field.name]" :id="'error-' + field.name" class="field-error">{{ errors[field.name] }}</small>
              </label>
            </div>
          </div>
          <div class="drawer-footer"><button type="button" class="button" @click="closeDrawer" :disabled="busy">Отмена</button><button class="button primary" :disabled="busy"><Icon :name="busy ? 'refresh' : 'check'" :size="17" :class="{ spinning: busy }"/>{{ busy ? 'Сохранение…' : 'Сохранить запись' }}</button></div>
        </form>
        <template v-else>
          <div class="drawer-tabs"><button :class="{ active: detailTab === 'info' }" @click="detailTab = 'info'">Карточка</button><button v-if="['equipment', 'work-orders'].includes(resource.key)" :class="{ active: detailTab === 'history' }" @click="detailTab = 'history'">История</button><button v-if="resource.key === 'equipment'" :class="{ active: detailTab === 'related' }" @click="detailTab = 'related'">Заявки и ТО</button><button v-if="resource.key === 'work-orders'" :class="{ active: detailTab === 'materials' }" @click="detailTab = 'materials'">Материалы <span>{{ materials.length }}</span></button></div>
          <div class="drawer-body">
            <div v-if="detailsLoading" class="loading-panel"><span class="spinner"></span>Загружаем карточку…</div>
            <template v-else-if="detailTab === 'info'">
              <span v-if="selected?.Status" class="status-badge detail-status" :class="badge(selected.Status)">{{ selected.Status }}</span>
              <dl class="detail-list"><div v-for="field in infoFields" :key="field.name"><dt>{{ field.label }}</dt><dd>{{ field.name === 'Number' ? selected.DisplayNumber || display(selected[field.name], field) : display(selected[field.name], field) }}</dd></div></dl>
              <section v-if="resource.key === 'schedule' && ['admin', 'engineer', 'master'].includes(user?.Role)" class="action-box">
                <h3>Создать плановую заявку</h3><p class="form-help">Повторное действие открывает уже связанную заявку. Правила доступности проверяет сервер.</p>
                <form @submit.prevent="createScheduleOrder">
                  <label>Ответственный мастер<select v-model="orderMaster" required :disabled="user?.Role === 'master'"><option value="">Выберите мастера</option><option v-for="person in masterOptions" :key="person.id" :value="person.id">{{ person.label }}</option></select></label>
                  <label>Плановое начало заявки (UTC)<input v-model="scheduleStart" type="datetime-local" step="1" required></label>
                  <label>Длительность, часов<input v-model="scheduleHours" type="number" min="0.01" step="any" placeholder="По умолчанию — из вида ТО"></label>
                  <p class="form-help">Если дата ТО уже прошла, укажите новое плановое начало. Исходная дата графика не изменяется.</p>
                  <button class="button primary small" :disabled="busy || !orderMaster">Создать / открыть заявку</button>
                </form>
              </section>
              <section v-if="canTransition && allowedTransitions.length" class="action-box">
                <h3>Изменить статус заявки</h3>
                <form @submit.prevent="changeStatus">
                  <label>Следующий этап<select v-model="transition.status" required><option value="">Выберите статус</option><option v-for="item in allowedTransitions" :key="item">{{ item }}</option></select></label>
                  <label v-if="transition.status === 'назначена'">Ответственная бригада<select v-model="transition.team_id" required><option value="">Выберите бригаду</option><option v-for="x in lookups.teams || []" :key="x.id" :value="x.id">{{ x.label }}</option></select></label>
                  <label v-if="transition.status === 'в работе' && !selected.ActualStart">Фактическое начало (UTC)<input v-model="transition.actual_start" type="datetime-local" step="1" required></label>
                  <template v-if="transition.status === 'выполнена'"><label>Фактическое окончание (UTC)<input v-model="transition.actual_end" type="datetime-local" step="1" required></label><label>Отчёт о выполненных работах<textarea v-model="transition.completion_report" rows="3" required></textarea></label></template>
                  <button class="button primary small" :disabled="busy || !transition.status">Применить статус<Icon name="arrow" :size="16"/></button>
                </form>
              </section>
            </template>
            <template v-else-if="detailTab === 'history'">
              <ol v-if="history.length" class="timeline"><li v-for="(entry, index) in history" :key="entry.Id || index"><span class="timeline-point"></span><div><time>{{ date(entry.ChangedAt || entry.OccurredAt) }}</time><p><span v-if="entry.OldStatus">{{ entry.OldStatus }}<Icon name="arrow" :size="14"/></span><strong>{{ entry.NewStatus || entry.Action }}</strong></p><small v-if="entry.ChangedByName || entry.ActorName || entry.ChangedBy">{{ entry.ChangedByName || entry.ActorName || `Пользователь #${entry.ChangedBy}` }}</small></div></li></ol><div v-else class="list-empty">История изменений пока пуста</div>
            </template>
            <template v-else-if="detailTab === 'related'">
              <h3>История заявок</h3><DataTable :rows="related.orders || []" :columns="[{ key: 'DisplayNumber', label: 'Заявка' }, { key: 'Status', label: 'Статус', type: 'status' }, { key: 'CreatedAt', label: 'Создано', type: 'date' }]" clickable @select="row => emit('navigate', { page: 'work-orders', id: row.Id })"/>
              <h3 class="related-heading">История обслуживания</h3><DataTable :rows="related.schedule || []" :columns="[{ key: 'PlannedAt', label: 'Дата ТО', type: 'date' }, { key: 'MaintenanceTypeName', label: 'Вид ТО' }, { key: 'Status', label: 'Статус', type: 'status' }]" clickable @select="row => emit('navigate', { page: 'schedule', id: row.Id })"/>
            </template>
            <template v-else-if="detailTab === 'materials'">
              <div class="materials-total"><span>Стоимость списанных материалов</span><strong>{{ number(totalMaterialCost, 2) }} ₽</strong></div>
              <div class="material-items"><div v-for="row in materials" :key="row.MaterialId" class="material-item"><div><strong>{{ row.MaterialName || lookups.materials?.find(x => x.id === row.MaterialId)?.label || `Материал #${row.MaterialId}` }}</strong><small>{{ number(row.Quantity, 3) }} × {{ number(row.UnitPrice, 2) }} ₽ = {{ number(row.Quantity * row.UnitPrice, 2) }} ₽</small></div><div v-if="canMaterials" class="material-controls"><input type="number" min="0.001" step="any" :value="row._quantity ?? row.Quantity" @input="row._quantity = $event.target.value" aria-label="Количество материала"><button class="icon-button" @click="updateMaterial({ ...row, _quantity: row._quantity ?? row.Quantity })" :disabled="busy" title="Сохранить количество" aria-label="Сохранить количество"><Icon name="check" :size="17"/></button><button class="icon-button danger-hover" @click="removeMaterial(row)" :disabled="busy" title="Удалить материал" aria-label="Удалить материал"><Icon name="delete" :size="17"/></button></div></div><div v-if="!materials.length" class="list-empty">Материалы ещё не добавлены</div></div>
              <section v-if="canMaterials" class="action-box"><h3>Списать материал</h3><form @submit.prevent="saveMaterial"><label>Материал<select v-model="materialForm.MaterialId" required><option value="">Выберите материал</option><option v-for="item in lookups.materials || []" :key="item.id" :value="item.id">{{ item.label }}</option></select></label><div class="form-grid"><label>Количество<input v-model="materialForm.Quantity" type="number" min="0.001" step="any" required></label><label>Комментарий<input v-model="materialForm.Comment" type="text"></label></div><button class="button primary small" :disabled="busy"><Icon name="plus" :size="16"/>Добавить в заявку</button></form></section>
            </template>
          </div>
          <div class="drawer-footer"><button class="button" @click="closeDrawer">Закрыть</button><button v-if="resource.canWrite" class="button primary" @click="openEdit()"><Icon name="edit" :size="16"/>Редактировать</button></div>
        </template>
      </section>
    </div>
    <div v-if="deleteTarget" class="modal-backdrop" @click.self="!busy && (deleteTarget = null)">
      <section class="confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="delete-title"><span class="metric-icon rose"><Icon name="delete" :size="24"/></span><h2 id="delete-title">Удалить запись?</h2><p>«{{ deleteTarget.Name || deleteTarget.DisplayNumber || deleteTarget.Number || deleteTarget.Email || '#' + deleteTarget.Id }}» будет удалена или деактивирована. Связанные данные защищены правилами системы.</p><div v-if="deleteError" class="alert error" role="alert">{{ deleteError }}</div><div class="confirm-actions"><button class="button" @click="deleteTarget = null" :disabled="busy">Отмена</button><button class="button danger" @click="remove" :disabled="busy">{{ busy ? 'Удаление…' : 'Удалить' }}</button></div></section>
    </div>
  </section>
</template>
