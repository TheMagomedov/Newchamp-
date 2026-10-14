<script setup>
import { ref, watch, onMounted } from 'vue';
import Icon from './Icon.vue';
import DataTable from './DataTable.vue';
import { request, query, download } from './api.js';
import { readable, number } from './format.js';
defineProps({ lookups: Object });
const emit = defineEmits(['notify']);
const filters = ref({ from: '', to: '', workshop_id: '' });
const reportType = ref('work-orders'); const format = ref('pdf');
const busy = ref(false); const error = ref(''); const preview = ref(null); const loading = ref(false);
const reports = [
  { key: 'work-orders', title: 'Выполнение работ', text: 'Заявки на обслуживание и ремонт.', icon: 'orders' },
  { key: 'downtime', title: 'Простои оборудования', text: 'Простои и потери рабочего времени.', icon: 'clock' },
  { key: 'schedule', title: 'Выполнение графика ТО', text: 'План, факт и соблюдение сроков.', icon: 'calendar' },
  { key: 'material-usage', title: 'Расход материалов', text: 'Списания и затраты за период.', icon: 'directory' },
  { key: 'team-efficiency', title: 'Эффективность бригад', text: 'Выполнение работ и рейтинг.', icon: 'users' },
  { key: 'equipment', title: 'Реестр оборудования', text: 'Характеристики и текущее состояние.', icon: 'equipment' },
  { key: 'materials', title: 'Складские остатки', text: 'Текущее наличие материалов.', icon: 'directory' },
  { key: 'analytics', title: 'Полная аналитика', text: 'Все аналитические разделы в одном файле.', icon: 'analytics' },
];
async function exportReport() {
  busy.value = true; error.value = '';
  try {
    const result = await request('reports/export', { method: 'POST', body: { type: reportType.value, format: format.value, ...Object.fromEntries(Object.entries(filters.value).filter(([, v]) => v !== '')) } });
    await download(result.url, result.filename || `toir-${reportType.value}.${format.value}`);
    emit('notify', 'Отчёт сформирован и скачан');
  } catch (e) { error.value = e.message; } finally { busy.value = false; }
}
let loadId = 0;
async function loadPreview() {
  const id = ++loadId; loading.value = true; error.value = '';
  try { const result = await request(`reports/preview?${query({ type: reportType.value, ...filters.value })}`); if (id === loadId) preview.value = result; }
  catch (e) { if (id === loadId) error.value = e.message; }
  finally { if (id === loadId) loading.value = false; }
}
watch(reportType, loadPreview);
onMounted(loadPreview);
</script>
<template>
  <section>
    <div class="page-heading"><div><p class="eyebrow">ОТЧЁТНОСТЬ</p><h1>Отчёты и экспорт</h1><p>Проверьте выборку, затем скачайте PDF, Excel или CSV.</p></div><span class="page-symbol"><Icon name="report" :size="28"/></span></div>
    <div class="report-types expanded-report-types"><button v-for="report in reports" :key="report.key" class="report-type" :class="{ selected: reportType === report.key }" @click="reportType = report.key"><span class="metric-icon teal"><Icon :name="report.icon" :size="22"/></span><strong>{{ report.title }}</strong><span>{{ report.text }}</span><span class="report-selected"><Icon v-if="reportType === report.key" name="check" :size="15"/></span></button></div>
    <section class="panel report-options"><div class="panel-heading"><div><h2>Параметры отчёта</h2><p>Включены только данные, доступные вашей роли. Период не изменяет текущие складские остатки.</p></div></div>
      <form @submit.prevent="exportReport"><div class="form-grid"><label>Дата начала<input v-model="filters.from" type="date" :max="filters.to || undefined"></label><label>Дата окончания<input v-model="filters.to" type="date" :min="filters.from || undefined"></label><label>Производственный цех<select v-model="filters.workshop_id"><option value="">Все доступные цеха</option><option v-for="item in lookups.workshops || []" :key="item.id" :value="item.id">{{ item.label }}</option></select></label><label>Формат документа<select v-model="format"><option value="pdf">PDF — для печати</option><option value="xlsx">Excel (.xlsx) — для анализа</option><option value="csv">CSV — обмен данными</option></select></label></div>
        <div v-if="error" class="alert error" role="alert"><Icon name="alert"/>{{ error }}</div><div class="report-actions"><button type="button" class="button" @click="loadPreview" :disabled="loading"><Icon name="refresh" :size="16" :class="{ spinning: loading }"/>Предпросмотр</button><button class="button primary" :disabled="busy"><Icon :name="busy ? 'refresh' : 'download'" :class="{ spinning: busy }" :size="18"/>{{ busy ? 'Формируем отчёт…' : 'Сформировать и скачать' }}</button></div>
      </form>
    </section>
    <section class="panel summary-panel"><div class="panel-heading"><div><h2>{{ preview?.title || 'Предварительный просмотр' }}</h2><p>Сортировка и поиск ниже не меняют состав серверного экспорта.</p></div></div><div v-if="loading" class="loading-panel"><span class="spinner"></span>Рассчитываем…</div><template v-else-if="preview"><div v-if="preview.summary" class="preview-summary"><template v-for="(value, key) in preview.summary" :key="key"><span v-if="typeof value !== 'object'">{{ readable(key) }}<strong>{{ typeof value === 'number' ? number(value, 2) : value }}</strong></span></template></div><DataTable :rows="preview.rows || []" :columns="preview.columns || []" :filename="reportType" :title="preview.title"/></template></section>
  </section>
</template>
