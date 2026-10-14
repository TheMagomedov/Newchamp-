<script setup>
import { ref, computed, watch } from 'vue';
import { request, query } from './api.js';
import { monthDays, shiftMonth } from './data.js';
import { badge } from './format.js';
const props = defineProps({ workshop: [String, Number], workshops: String, equipment: [String, Number], status: String, orderType: String, priority: String, revision: Number, rows: Array, initialDate: String });
const emit = defineEmits(['select', 'period']);
const month = ref(props.initialDate?.slice(0, 7) || new Date().toISOString().slice(0, 7));
const items = ref([]); const loading = ref(false); const error = ref(''); let requestId = 0;
const days = computed(() => monthDays(month.value));
const title = computed(() => new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${month.value}-01T12:00:00Z`)));
const cells = computed(() => days.value.map(day => ({ ...day, rows: (props.rows || items.value).filter(row => row.PlannedAt?.slice(0, 10) === day.value) })));
function visibleStatus(row) { return !['выполнено', 'отменено'].includes(row.Status) && new Date(row.PlannedAt.replace(/Z$/, '') + 'Z') < new Date() ? 'просрочено' : row.Status; }
async function load() {
  const id = ++requestId; loading.value = true; error.value = '';
  const from = `${month.value}-01`; const to = new Date(Date.UTC(Number(month.value.slice(0, 4)), Number(month.value.slice(5)), 0)).toISOString().slice(0, 10);
  emit('period', { from, to });
  if (props.rows) { loading.value = false; return; }
  try {
    const rows = []; let page = 1; let total = Infinity;
    while (rows.length < total) {
      const data = await request(`schedule?${query({ from, to, workshop_id: props.workshop, workshop_ids: props.workshops, equipment_id: props.equipment, type: props.orderType, priority: props.priority, status: props.status, page, page_size: 100 })}`);
      if (id !== requestId) return;
      rows.push(...data.items); total = data.total; page++;
      if (!data.items.length) break;
    }
    items.value = rows;
  } catch (e) { if (id === requestId) error.value = e.message; }
  finally { if (id === requestId) loading.value = false; }
}
watch([month, () => props.workshop, () => props.workshops, () => props.equipment, () => props.status, () => props.orderType, () => props.priority, () => props.revision], load, { immediate: true });
</script>
<template>
  <section class="panel calendar-panel"><div class="panel-heading"><div><h2>Календарь обслуживания</h2><p>Нажмите на работу, чтобы открыть карточку</p></div><div class="calendar-nav"><button class="button small" aria-label="Предыдущий месяц" @click="month = shiftMonth(month, -1)">←</button><label><span class="visually-hidden">Месяц календаря</span><input v-model="month" type="month" required></label><button class="button small" aria-label="Следующий месяц" @click="month = shiftMonth(month, 1)">→</button></div></div>
    <div v-if="error" class="alert error" role="alert">{{ error }}<button class="text-button" @click="load">Повторить</button></div>
    <p class="calendar-caption">{{ title }} <span v-if="loading">· загрузка…</span></p>
    <div class="calendar-scroll"><div class="calendar-grid"><div class="calendar-weekday" v-for="day in ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']" :key="day">{{ day }}</div><div v-for="cell in cells" :key="cell.value" class="calendar-day" :class="{ muted: !cell.current, today: cell.value === new Date().toISOString().slice(0, 10) }"><span>{{ cell.day }}</span><button v-for="row in cell.rows" :key="row.Id" class="calendar-event" :class="badge(visibleStatus(row))" @click="emit('select', row)" :title="`${row.EquipmentName || row.EquipmentId}: ${row.Status}`">{{ row.EquipmentName || row.InventoryNumber || `#${row.EquipmentId}` }}<small>{{ visibleStatus(row) }}</small></button></div></div></div>
    <div class="calendar-legend"><span class="status-badge warning">Запланировано</span><span class="status-badge info">В работе</span><span class="status-badge success">Выполнено</span><span class="status-badge danger">Просрочено</span></div>
  </section>
</template>
