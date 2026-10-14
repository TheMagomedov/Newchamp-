<script setup>
import { ref, computed, watch } from 'vue';
import { tableRows, csvText, saveBlob } from './data.js';
import { number, date, badge } from './format.js';
const props = defineProps({ rows: { default: () => [] }, columns: { default: () => [] }, title: String, filename: { default: 'data' }, clickable: Boolean });
const emit = defineEmits(['select']);
const search = ref(''); const sort = ref(''); const direction = ref('asc'); const page = ref(1); const size = ref(25);
const filtered = computed(() => tableRows(props.rows, search.value, sort.value, direction.value));
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / size.value)));
const visible = computed(() => filtered.value.slice((page.value - 1) * size.value, page.value * size.value));
watch([search, size, () => props.rows], () => { page.value = 1; });
function order(key) { direction.value = sort.value === key && direction.value === 'asc' ? 'desc' : 'asc'; sort.value = key; }
function display(value, column, row) {
  if (column.key === 'Number' || column.key === 'DisplayNumber') return row.DisplayNumber || row.Number || '—';
  if (column.key === 'severity') return ({ danger: 'Критично', warning: 'Внимание', info: 'Информация', success: 'Выполнено' })[value] || value;
  return column.type === 'date' ? date(value) : typeof value === 'number' ? number(value, column.decimals ?? 2) : value ?? '—';
}
function exportCSV() {
  const rows = filtered.value.map(row => ({ ...row, ...(row.DisplayNumber ? { Number: row.DisplayNumber } : {}) }));
  saveBlob(new Blob([csvText(rows, props.columns)], { type: 'text/csv;charset=utf-8' }), `${props.filename}.csv`);
}
</script>
<template>
  <div class="data-table">
    <div class="data-tools"><label><span class="visually-hidden">Поиск: {{ title || 'таблица' }}</span><input v-model="search" type="search" placeholder="Поиск в таблице…"></label><button class="button small" @click="exportCSV">CSV</button></div>
    <div class="table-scroll"><table><caption v-if="title" class="visually-hidden">{{ title }}</caption><thead><tr><th v-for="column in columns" :key="column.key" :aria-sort="sort === column.key ? direction === 'asc' ? 'ascending' : 'descending' : 'none'"><button class="sort-button" @click="order(column.key)">{{ column.label }} {{ sort === column.key ? direction === 'asc' ? '↑' : '↓' : '↕' }}</button></th></tr></thead>
      <tbody><tr v-for="(row, index) in visible" :key="row.Id || row.id || index"><td v-for="(column, i) in columns" :key="column.key"><button v-if="clickable && i === 0" class="cell-link" @click="emit('select', row)">{{ display(row[column.key], column, row) }}</button><span v-else-if="column.type === 'status'" class="status-badge" :class="badge(row[column.key])">{{ display(row[column.key], column, row) }}</span><span v-else>{{ display(row[column.key], column, row) }}</span></td></tr><tr v-if="!visible.length"><td :colspan="columns.length" class="empty-cell">По выбранным условиям данных нет</td></tr></tbody></table></div>
    <div class="pagination"><span>{{ filtered.length }} записей</span><div><label>Строк<select v-model.number="size"><option :value="25">25</option><option :value="50">50</option><option :value="100">100</option></select></label><button class="button small" :disabled="page === 1" aria-label="Предыдущая страница" @click="page--">←</button><span>{{ page }} / {{ pageCount }}</span><button class="button small" :disabled="page >= pageCount" aria-label="Следующая страница" @click="page++">→</button></div></div>
  </div>
</template>
