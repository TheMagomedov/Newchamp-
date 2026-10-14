<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import Icon from './Icon.vue';
import ChartPanel from './ChartPanel.vue';
import DataTable from './DataTable.vue';
import MaintenanceCalendar from './MaintenanceCalendar.vue';
import { request, query, download } from './api.js';
import { filterQuery } from './data.js';
import { number } from './format.js';

const props = defineProps({ analytics: Boolean, lookups: Object, user: Object });
const emit = defineEmits(['navigate', 'notify']);
const data = ref(null); const loading = ref(false); const error = ref(''); const updated = ref(null);
const notices = ref([]); const exporting = ref(''); const templateName = ref(''); const selectedTemplate = ref('');
const today = new Date().toISOString().slice(0, 10);
const emptyFilters = () => ({ from: new Date(Date.now() - 29 * 86400000).toISOString().slice(0, 10), to: today, workshop_ids: [], type: '', priority: '', equipment_id: '' });
const filters = ref(emptyFilters()); const applied = ref(emptyFilters());
const templates = ref([]); const storageKey = `toir-analytics-filters-${props.user?.Id}`;
try { templates.value = JSON.parse(localStorage.getItem(storageKey) || '[]'); } catch { templates.value = []; }
let poll; let controller; let requestId = 0; let eventTimer;
const m = computed(() => data.value?.metrics || {});
const schedule = computed(() => data.value?.schedule || {});
const metrics = computed(() => [
  { key: 'equipment', title: 'Оборудование', value: m.value.equipment, icon: 'equipment', tone: 'teal', page: 'equipment', scope: 'Текущее состояние' },
  { key: 'open_orders', title: 'Активные заявки', value: m.value.open_orders, icon: 'orders', tone: 'blue', page: 'work-orders', scope: 'Текущее состояние' },
  { key: 'completed_orders', title: 'Выполнено заявок', value: m.value.completed_orders, icon: 'check', tone: 'teal', page: 'work-orders', scope: 'За выбранный период' },
  { key: 'downtime_hours', title: 'Простои, ч', value: m.value.downtime_hours, icon: 'clock', tone: 'amber', page: 'equipment', scope: 'За выбранный период' },
  { key: 'avg_completion_hours', title: 'Среднее время, ч', value: m.value.avg_completion_hours, icon: 'analytics', tone: 'blue', page: 'work-orders', scope: 'Завершённые работы' },
  { key: 'adherence_percent', title: 'Выполнение ТО, %', value: schedule.value.adherence_percent, icon: 'calendar', tone: 'rose', page: 'schedule', scope: 'От плановых работ' },
]);
const orderColumns = [{ key: 'Number', label: 'Заявка' }, { key: 'EquipmentName', label: 'Оборудование' }, { key: 'Status', label: 'Статус', type: 'status' }, { key: 'Priority', label: 'Приоритет', type: 'status' }, { key: 'CreatedAt', label: 'Создано', type: 'date' }];
const downtimeColumns = [{ key: 'label', label: 'Оборудование' }, { key: 'inventory_number', label: 'Инв. номер' }, { key: 'hours', label: 'Простой, ч' }];
const materialColumns = [{ key: 'label', label: 'Материал' }, { key: 'code', label: 'Код' }, { key: 'quantity', label: 'Расход' }, { key: 'unit', label: 'Ед.' }, { key: 'cost', label: 'Стоимость, ₽' }];
const scheduleColumns = [{ key: 'label', label: 'Цех' }, { key: 'planned', label: 'План' }, { key: 'completed', label: 'Факт' }, { key: 'on_time', label: 'В срок' }, { key: 'overdue', label: 'Просрочено' }, { key: 'adherence_percent', label: 'Выполнение, %' }];
const teamColumns = [{ key: 'rank', label: 'Место' }, { key: 'label', label: 'Бригада' }, { key: 'completed', label: 'Выполнено' }, { key: 'active', label: 'Активно' }, { key: 'avg_completion_hours', label: 'Среднее, ч' }, { key: 'on_time_percent', label: 'В срок, %' }];
const teams = computed(() => (data.value?.team_rankings || []).map((row, index) => ({ ...row, rank: index + 1 })));
const timelineLabel = computed(() => `Последние 30 дней выбранного периода: ${(data.value?.period?.timeline_from || applied.value.from).slice(0, 10)} — ${applied.value.to}`);
function rows(key, value = 'value', limit = Infinity) { return (data.value?.[key] || []).slice(0, limit).map(row => ({ ...row, label: row.label || row.date, value: row[value] })); }
function trend(key) {
  const value = data.value?.trends?.[key] || data.value?.kpi_trends?.[key];
  if (!value || value.available === false) return value?.reason || 'Нет исторического сравнения';
  if (value.percent == null) return `Ранее: ${number(value.previous, 1)} · изменение ${number(value.delta, 1)}`;
  return `${value.percent > 0 ? '↑' : value.percent < 0 ? '↓' : '→'} ${number(Math.abs(value.percent), 1)}% к предыдущему периоду`;
}
function goto(page, extra = {}, id) {
  const scope = filterQuery(applied.value);
  if (!['work-orders', 'schedule'].includes(page)) { delete scope.from; delete scope.to; delete scope.type; delete scope.priority; }
  emit('navigate', { page, id, filters: { ...scope, ...extra } });
}
async function load(silent = false) {
  const id = ++requestId; controller?.abort(); const current = new AbortController(); controller = current;
  if (!silent) loading.value = true;
  error.value = '';
  const requested = JSON.parse(JSON.stringify(filters.value));
  try {
    const result = await request(`analytics/dashboard?${query(filterQuery(requested))}`, { signal: current.signal });
    if (id !== requestId) return;
    data.value = result; applied.value = requested; updated.value = new Date();
    if (!props.analytics) {
      try { const result = await request('notifications', { signal: current.signal }); if (id === requestId) notices.value = result.items || []; } catch (e) { if (e.name !== 'AbortError') error.value = e.message; }
    }
  } catch (e) { if (id === requestId && e.name !== 'AbortError') error.value = e.message; }
  finally { if (id === requestId) loading.value = false; }
}
function reset() { filters.value = emptyFilters(); selectedTemplate.value = ''; load(); }
function preset(kind) {
  const date = new Date();
  if (kind === 'quarter') filters.value.from = new Date(Date.UTC(date.getUTCFullYear(), Math.floor(date.getUTCMonth() / 3) * 3, 1)).toISOString().slice(0, 10);
  else if (kind === 'year') filters.value.from = `${date.getUTCFullYear()}-01-01`;
  else filters.value.from = emptyFilters().from;
  filters.value.to = today; load();
}
function saveTemplate() {
  const name = templateName.value.trim(); if (!name) return;
  templates.value = [...templates.value.filter(x => x.name !== name), { name, filters: JSON.parse(JSON.stringify(filters.value)) }].slice(-20);
  localStorage.setItem(storageKey, JSON.stringify(templates.value)); templateName.value = ''; selectedTemplate.value = name; emit('notify', 'Шаблон фильтров сохранён');
}
function applyTemplate() { const value = templates.value.find(x => x.name === selectedTemplate.value); if (value) { filters.value = JSON.parse(JSON.stringify(value.filters)); load(); } }
function removeTemplate() { templates.value = templates.value.filter(x => x.name !== selectedTemplate.value); localStorage.setItem(storageKey, JSON.stringify(templates.value)); selectedTemplate.value = ''; }
async function exportPDF(block = 'all') {
  exporting.value = block; error.value = '';
  try {
    const { type: order_type, ...reportFilters } = filterQuery(applied.value);
    const result = await request('reports/export', { method: 'POST', body: { type: 'analytics', block, format: 'pdf', order_type, ...reportFilters } });
    await download(result.url, `analytics-${block}.pdf`); emit('notify', 'Аналитический отчёт PDF скачан');
  } catch (e) { error.value = e.message; } finally { exporting.value = ''; }
}
function revision() { clearTimeout(eventTimer); eventTimer = setTimeout(() => load(true), 300); }
function printPage() { window.print(); }
onMounted(() => { load(); poll = setInterval(() => { if (!document.hidden) load(true); }, 60000); window.addEventListener('toir-revision', revision); });
onUnmounted(() => { requestId++; clearInterval(poll); clearTimeout(eventTimer); controller?.abort(); window.removeEventListener('toir-revision', revision); });
</script>

<template>
  <section>
    <div class="page-heading"><div><p class="eyebrow">{{ analytics ? 'ДАННЫЕ ДЛЯ РЕШЕНИЙ' : 'ЦЕНТР УПРАВЛЕНИЯ' }}</p><h1>{{ analytics ? 'Аналитика обслуживания' : 'Обзор предприятия' }}</h1><p>{{ analytics ? 'От показателя — к первичной записи. Все расчёты выполняет сервер.' : 'Состояние оборудования, выполнение работ и риски предприятия.' }}</p></div><div class="heading-actions"><button class="button" @click="load()" :disabled="loading" aria-label="Обновить" title="Обновить"><Icon name="refresh" :size="17" :class="{ spinning: loading }"/>Обновить</button><button class="button" @click="exportPDF('all')" :disabled="!!exporting || !data"><Icon name="download" :size="17"/>PDF всей аналитики</button><button class="button" @click="printPage" :disabled="!data">Печать страницы</button></div></div>
    <details class="panel analytic-filters" :open="analytics"><summary class="filters-summary">Фильтры: {{ applied.from }} — {{ applied.to }}<span>Период, цеха и оборудование</span></summary><form @submit.prevent="load()"><div class="analysis-filter-grid"><label>Период с<input type="date" v-model="filters.from" :max="filters.to || undefined" required></label><label>по<input type="date" v-model="filters.to" :min="filters.from || undefined" required></label><label>Цеха <small>Ctrl / ⌘ — несколько</small><select v-model="filters.workshop_ids" multiple size="3" aria-label="Цеха: множественный выбор"><option v-for="row in lookups?.workshops || []" :key="row.id" :value="String(row.id)">{{ row.label }}</option></select></label><label>Тип заявки<select v-model="filters.type"><option value="">Все типы</option><option>текущая</option><option>плановая</option><option>аварийная</option></select></label><label>Оборудование<select v-model="filters.equipment_id"><option value="">Всё оборудование</option><option v-for="row in lookups?.equipment || []" :key="row.id" :value="row.id">{{ row.label }}</option></select></label><label>Приоритет<select v-model="filters.priority"><option value="">Все приоритеты</option><option>низкий</option><option>средний</option><option>высокий</option><option>критический</option></select></label></div><div class="filter-actions"><button class="button primary small" :disabled="loading">Применить</button><button type="button" class="button small" @click="reset">Сбросить</button><button type="button" class="text-button" @click="preset('month')">30 дней</button><button type="button" class="text-button" @click="preset('quarter')">Квартал</button><button type="button" class="text-button" @click="preset('year')">Год</button><span class="muted">Нет выбранных цехов = все доступные</span></div></form>
      <div v-if="analytics" class="template-toolbar"><label><span class="visually-hidden">Название шаблона</span><input v-model="templateName" maxlength="60" placeholder="Название шаблона"></label><button class="button small" :disabled="!templateName.trim()" @click="saveTemplate">Сохранить фильтры</button><label><span class="visually-hidden">Сохранённый шаблон</span><select v-model="selectedTemplate"><option value="">Сохранённые шаблоны</option><option v-for="item in templates" :key="item.name">{{ item.name }}</option></select></label><button class="button small" :disabled="!selectedTemplate" @click="applyTemplate">Применить шаблон</button><button class="text-button" :disabled="!selectedTemplate" @click="removeTemplate">Удалить</button></div>
    </details>
    <div v-if="error" class="alert error" role="alert"><Icon name="alert"/><span>{{ error }}</span><button class="text-button" @click="load()">Повторить</button></div>
    <div v-if="loading && !data" class="loading-panel"><span class="spinner"></span>Рассчитываем показатели…</div>
    <template v-if="data">
      <div class="metrics-grid six-metrics"><button v-for="item in metrics" :key="item.key" class="metric-card" @click="goto(item.page)"><span class="metric-top"><span>{{ item.title }}</span><span class="metric-icon" :class="item.tone"><Icon :name="item.icon" :size="21"/></span></span><strong class="metric-value">{{ item.value == null ? '—' : number(item.value, 1) }}</strong><span class="metric-note">{{ item.scope }}</span><span class="metric-trend">{{ trend(item.key) }}</span></button></div>
      <div class="dashboard-grid"><ChartPanel title="Оборудование по статусам" kind="donut" :rows="data.equipment_status" @select="row => goto('equipment', { status: row.label })" @error="error = $event"/><ChartPanel title="Заявки по цехам" :rows="data.orders_by_workshop" @select="row => goto('work-orders', { workshop_id: row.workshop_id, workshop_ids: '' })" @error="error = $event"/></div>
      <template v-if="!analytics">
        <div class="dashboard-grid"><ChartPanel title="Динамика заявок" :subtitle="timelineLabel" kind="line" :rows="rows('orders_daily', 'created')" @select="row => goto('work-orders', { from: row.date, to: row.date })" @error="error = $event"/><ChartPanel title="Топ-5 оборудования по простоям" unit="ч" :rows="rows('top_downtime', 'hours', 5)" @select="row => goto('equipment', {}, row.equipment_id)" @error="error = $event"/></div>
        <section class="panel section-gap"><div class="panel-heading"><div><h2>10 последних заявок</h2><p>Статусы, приоритеты и переход к первичным данным</p></div></div><DataTable title="Последние заявки" :rows="data.recent_orders" :columns="orderColumns" clickable @select="row => goto('work-orders', {}, row.Id)"/></section>
        <section class="panel section-gap"><div class="panel-heading"><div><h2>Нарушения и просрочки</h2><p>Текущие предупреждения по доступным объектам</p></div><span class="tag">{{ notices.length }}</span></div><DataTable title="Нарушения и просрочки" :rows="notices" :columns="[{ key: 'title', label: 'Событие' }, { key: 'message', label: 'Подробности' }, { key: 'severity', label: 'Важность' }]" clickable @select="row => goto(row.resource, {}, row.entity_id)"/></section>
      </template>
      <template v-else>
        <section class="analytic-section"><div class="section-heading"><div><p class="eyebrow">01 / ЗАЯВКИ</p><h2>Объём и структура работ</h2></div><button class="button small" :disabled="!!exporting" @click="exportPDF('orders')">PDF блока</button></div><div class="dashboard-grid"><ChartPanel title="Заявки по типам" kind="donut" :rows="data.orders_by_type" @select="row => goto('work-orders', { type: row.label })" @error="error = $event"/><ChartPanel title="Заявки по приоритетам" kind="donut" :rows="data.orders_by_priority || data.orders_by_priorities" @select="row => goto('work-orders', { priority: row.label })" @error="error = $event"/></div><div class="dashboard-grid"><section class="panel"><div class="panel-heading"><h2>Заявки по статусам</h2></div><DataTable :rows="data.orders_by_status" :columns="[{ key: 'label', label: 'Статус' }, { key: 'value', label: 'Количество' }]" filename="orders-status" clickable @select="row => goto('work-orders', { status: row.label })"/></section><ChartPanel title="Динамика заявок" :subtitle="timelineLabel" kind="line" :rows="rows('orders_daily', 'created')" @select="row => goto('work-orders', { from: row.date, to: row.date })" @error="error = $event"/></div></section>
        <section class="analytic-section"><div class="section-heading"><div><p class="eyebrow">02 / НАДЁЖНОСТЬ</p><h2>Анализ простоев</h2></div><button class="button small" :disabled="!!exporting" @click="exportPDF('downtime')">PDF блока</button></div><div class="dashboard-grid"><ChartPanel title="Динамика простоев" :subtitle="timelineLabel" unit="ч" kind="line" :rows="rows('downtime_daily', 'hours')" @select="row => goto('work-orders', { from: row.date, to: row.date })" @error="error = $event"/><ChartPanel title="Топ-10 оборудования по простоям" unit="ч" :rows="rows('top_downtime', 'hours', 10)" @select="row => goto('equipment', {}, row.equipment_id)" @error="error = $event"/></div><section class="panel section-gap"><div class="panel-heading"><h2>Детализация простоев оборудования</h2><button class="button small" @click="goto('equipment')">Детализация</button></div><DataTable :rows="(data.top_downtime || []).slice(0, 10)" :columns="downtimeColumns" filename="downtime-top10" clickable @select="row => goto('equipment', {}, row.equipment_id)"/></section></section>
        <section class="analytic-section"><div class="section-heading"><div><p class="eyebrow">03 / ЗАТРАТЫ</p><h2>Расход материалов</h2></div><button class="button small" :disabled="!!exporting" @click="exportPDF('materials')">PDF блока</button></div><div class="dashboard-grid"><ChartPanel title="Топ-10 материалов по стоимости" unit="₽" :rows="rows('materials_top', 'cost', 10)" @select="row => goto('materials', {}, row.material_id)" @error="error = $event"/><ChartPanel title="Динамика расхода материалов" :subtitle="timelineLabel" unit="₽" kind="line" :rows="rows('materials_daily', 'cost')" @select="row => goto('work-orders', { from: row.date, to: row.date })" @error="error = $event"/></div><section class="panel section-gap"><div class="panel-heading"><h2>Расход и стоимость материалов</h2></div><DataTable :rows="data.materials_top" :columns="materialColumns" filename="materials-usage" clickable @select="row => goto('materials', {}, row.material_id)"/></section><section class="panel section-gap"><div class="panel-heading"><h2>Таблица динамики расхода</h2></div><DataTable :rows="data.materials_daily" :columns="[{ key: 'date', label: 'Дата', type: 'date' }, { key: 'cost', label: 'Расход, ₽' }]" filename="materials-daily"/></section></section>
        <section class="analytic-section"><div class="section-heading"><div><p class="eyebrow">04 / ПЛАНИРОВАНИЕ</p><h2>Выполнение графика ТО</h2></div><button class="button small" :disabled="!!exporting" @click="exportPDF('schedule')">PDF блока</button></div><div class="schedule-summary"><span>План <strong>{{ schedule.planned }}</strong></span><span>Выполнено <strong>{{ schedule.completed }}</strong></span><span>В срок <strong>{{ schedule.on_time }}</strong></span><span class="danger-text">Просрочено <strong>{{ schedule.overdue }}</strong></span></div><div class="dashboard-grid"><ChartPanel title="Выполнение ТО по цехам" unit="%" :rows="(schedule.by_workshop || []).map(row => ({ ...row, value: row.adherence_percent }))" @select="row => goto('schedule', { workshop_id: row.workshop_id, workshop_ids: '' })" @error="error = $event"/><section class="panel"><div class="panel-heading"><h2>Плановые и фактические ТО</h2></div><DataTable :rows="schedule.by_workshop" :columns="scheduleColumns" filename="maintenance-plan-fact" clickable @select="row => goto('schedule', { workshop_id: row.workshop_id, workshop_ids: '' })"/></section></div><MaintenanceCalendar :key="JSON.stringify(applied)" :initial-date="applied.from" :workshops="applied.workshop_ids.join(',')" :order-type="applied.type" :priority="applied.priority" :equipment="applied.equipment_id" @select="row => goto('schedule', {}, row.Id)"/></section>
        <section class="analytic-section"><div class="section-heading"><div><p class="eyebrow">05 / КОМАНДА</p><h2>Эффективность бригад</h2></div><button class="button small" :disabled="!!exporting" @click="exportPDF('teams')">PDF блока</button></div><div class="dashboard-grid"><ChartPanel title="Бригады: выполненные заявки" :rows="rows('team_rankings', 'completed')" @select="row => goto('teams', {}, row.team_id)" @error="error = $event"/><section class="panel"><div class="panel-heading"><h2>Рейтинг бригад</h2><p>По данным завершённых работ за период</p></div><DataTable :rows="teams" :columns="teamColumns" filename="team-rankings" clickable @select="row => goto('teams', {}, row.team_id)"/></section></div></section>
      </template>
      <p class="updated-at" v-if="updated">Обновлено {{ updated.toLocaleTimeString('ru-RU') }} · SSE и резервное обновление каждые 60 с · период {{ applied.from }} — {{ applied.to }}</p>
    </template>
  </section>
</template>
