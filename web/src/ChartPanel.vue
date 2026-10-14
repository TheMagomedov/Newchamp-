<script setup>
import { ref, computed } from 'vue';
import { number } from './format.js';
import { csvText, saveBlob } from './data.js';
const props = defineProps({ title: String, subtitle: String, rows: { default: () => [] }, kind: { default: 'bar' }, unit: { default: '' }, compact: Boolean });
const emit = defineEmits(['select', 'error']);
const svg = ref(null); const hover = ref(null);
const colors = ['#178478', '#e0a446', '#748cb1', '#bd6865', '#9a88ba', '#768c89'];
const values = computed(() => props.rows.filter(x => x.value != null).map(x => ({ ...x, label: String(x.label ?? x.date ?? ''), value: Number(x.value || 0) })));
const max = computed(() => Math.max(1, ...values.value.map(x => x.value)));
const total = computed(() => values.value.reduce((sum, x) => sum + x.value, 0));
const height = computed(() => props.kind === 'bar' ? Math.max(220, values.value.length * 34 + 30) : 230);
const points = computed(() => values.value.map((x, i) => ({ ...x, x: 42 + i * 520 / Math.max(1, values.value.length - 1), y: 184 - x.value / max.value * 148 })));
const line = computed(() => points.value.map(x => `${x.x},${x.y}`).join(' '));
const slices = computed(() => { let offset = 0; return values.value.map((x, i) => { const length = total.value ? x.value / total.value * 100 : 0; const item = { ...x, length, offset, color: colors[i % colors.length] }; offset += length; return item; }); });
function select(row) { hover.value = row; emit('select', row); }
function csv() { saveBlob(new Blob([csvText(values.value, [{ key: 'label', label: 'Показатель' }, { key: 'value', label: props.unit || 'Значение' }])], { type: 'text/csv;charset=utf-8' }), `${props.title}.csv`); }
async function png() {
  try {
    const clone = svg.value.cloneNode(true);
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.setAttribute('width', '1200'); clone.setAttribute('height', String(height.value * 2));
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml' }));
    try {
      const image = new Image(); image.src = url; await image.decode();
      const canvas = document.createElement('canvas'); canvas.width = 1200; canvas.height = height.value * 2 + 70;
      const ctx = canvas.getContext('2d'); ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#18313e'; ctx.font = '24px sans-serif'; ctx.fillText(props.title, 24, 40); ctx.drawImage(image, 0, 70);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
      if (!blob) throw new Error('Не удалось сформировать PNG');
      saveBlob(blob, `${props.title}.png`);
    } finally { URL.revokeObjectURL(url); }
  } catch (error) { emit('error', error.message); }
}
</script>
<template>
  <section class="panel chart-panel"><div class="panel-heading"><div><h2>{{ title }}</h2><p>{{ subtitle || 'Нажмите на значение для детализации' }}</p></div><div class="export-buttons"><button @click="csv" class="button small" :aria-label="`${title}: экспорт CSV`">CSV</button><button @click="png" class="button small" :aria-label="`${title}: экспорт PNG`">PNG</button></div></div>
    <div v-if="!values.length" class="chart-empty">Нет данных за выбранный период</div>
    <svg v-else ref="svg" :viewBox="`0 0 600 ${height}`" role="img" :aria-label="title" class="analytic-svg">
      <g v-if="kind === 'bar'" v-for="(row, i) in values" :key="i" tabindex="0" role="button" :aria-label="`${row.label}: ${row.value} ${unit}. Открыть детализацию`" @click="select(row)" @keydown.enter="select(row)" @keydown.space.prevent="select(row)" @mouseenter="hover = row" @mouseleave="hover = null">
        <title>{{ row.label }}: {{ number(row.value, 2) }} {{ unit }}</title><text x="12" :y="i * 34 + 27" font-size="11" fill="#48606c">{{ row.label.length > 24 ? row.label.slice(0, 23) + '…' : row.label }}</text><rect x="190" :y="i * 34 + 12" width="345" height="19" rx="4" fill="#eef3f4"/><rect x="190" :y="i * 34 + 12" :width="row.value / max * 345" height="19" rx="4" :fill="colors[i % colors.length]"/><text x="590" :y="i * 34 + 27" text-anchor="end" font-size="11" fill="#18313e">{{ number(row.value, 1) }}</text>
      </g>
      <g v-else-if="kind === 'line'">
        <path d="M42 25V184H575" fill="none" stroke="#b9c8ce"/><text x="35" y="35" text-anchor="end" font-size="10" fill="#617984">{{ number(max, 1) }}</text><text x="35" y="188" text-anchor="end" font-size="10" fill="#617984">0</text>
        <polyline :points="line" fill="none" stroke="#178478" stroke-width="3"/>
        <g v-for="(point, i) in points" :key="i" tabindex="0" role="button" :aria-label="`${point.label}: ${point.value}. Открыть детализацию`" @click="select(point)" @keydown.enter="select(point)" @keydown.space.prevent="select(point)" @mouseenter="hover = point" @mouseleave="hover = null"><title>{{ point.label }}: {{ number(point.value, 2) }} {{ unit }}</title><circle :cx="point.x" :cy="point.y" r="7" fill="#178478" stroke="white" stroke-width="2"/><text v-if="i === 0 || i === points.length - 1 || i % Math.max(1, Math.ceil(points.length / 5)) === 0" :x="point.x" y="210" text-anchor="middle" font-size="10" fill="#617984">{{ point.label.slice(5) || point.label }}</text></g>
      </g>
      <g v-else>
        <circle cx="125" cy="110" r="75" fill="none" stroke="#eef3f4" stroke-width="30"/>
        <circle v-for="(row, i) in slices" :key="i" cx="125" cy="110" r="75" fill="none" :stroke="row.color" stroke-width="30" pathLength="100" :stroke-dasharray="`${Math.max(0, row.length - .5)} ${100 - Math.max(0, row.length - .5)}`" :stroke-dashoffset="-row.offset" transform="rotate(-90 125 110)" tabindex="0" role="button" :aria-label="`${row.label}: ${row.value}. Открыть детализацию`" @click="select(row)" @keydown.enter="select(row)" @keydown.space.prevent="select(row)" @mouseenter="hover = row" @mouseleave="hover = null"><title>{{ row.label }}: {{ row.value }} ({{ number(row.length, 1) }}%)</title></circle>
        <text x="125" y="116" text-anchor="middle" font-size="29" fill="#18313e">{{ number(total) }}</text>
        <g v-for="(row, i) in slices" :key="`legend-${i}`"><circle cx="270" :cy="28 + i * 29" r="5" :fill="row.color"/><text x="284" :y="32 + i * 29" font-size="12" fill="#48606c">{{ row.label }}: {{ number(row.value, 1) }}</text></g>
      </g>
    </svg>
    <p class="chart-caption" aria-live="polite">{{ hover ? `${hover.label}: ${number(hover.value, 2)} ${unit}` : 'Данные из SQL Server · доступна детализация по клику' }}</p>
  </section>
</template>
