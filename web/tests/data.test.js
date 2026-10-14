import { test } from 'node:test';
import assert from 'node:assert/strict';
import { csvText, tableRows, filterQuery, monthDays, shiftMonth, parseSSE, fieldErrors } from '../src/data.js';

test('table search is case-insensitive for Russian labels and does not mutate source', () => {
  const rows = [{ label: 'Цех 10', count: 10 }, { label: 'Цех 2', count: 2 }, { label: 'Склад', count: 7 }];
  assert.deepEqual(tableRows(rows, 'ЦЕХ', 'count', 'asc').map(x => x.count), [2, 10]);
  assert.deepEqual(rows.map(x => x.count), [10, 2, 7]);
});
test('table sorting uses numeric ordering inside labels', () => {
  assert.deepEqual(tableRows([{ label: '№10' }, { label: '№2' }], '', 'label').map(x => x.label), ['№2', '№10']);
});
test('table sorting handles null values without crashing', () => {
  assert.equal(tableRows([{ value: null }, { value: 3 }], '', 'value', 'desc')[0].value, 3);
});
test('CSV quotes delimiters and line breaks and neutralizes spreadsheet formulas', () => {
  const result = csvText([{ a: '=SUM(1,2)', b: 'Код;"тест"\nстрока' }], [{ key: 'a', label: 'А' }, { key: 'b', label: 'Б' }]);
  assert.ok(result.startsWith('\ufeff'));
  assert.ok(result.includes('"\'=SUM(1,2)"'));
  assert.ok(result.includes('"Код;""тест""\nстрока"'));
});
test('CSV protects all spreadsheet formula prefixes', () => {
  for (const value of ['+1', '-1', '@SUM(A1)', '\t=1', '\r=1']) {
    assert.ok(csvText([{ value }], [{ key: 'value', label: 'Поле' }]).endsWith(`"'${value}"`));
  }
});
test('CSV keeps numeric negative values numeric rather than treating them as formulas', () => {
  assert.ok(csvText([{ value: -5 }], [{ key: 'value', label: 'Значение' }]).endsWith('"-5"'));
});
test('analytics filter query encodes multiple workshops and removes empty selectors', () => {
  assert.deepEqual(filterQuery({ workshop_ids: ['1', '3'], type: '', from: '2027-01-01', equipment_id: null, other: [] }), { workshop_ids: '1,3', from: '2027-01-01' });
});
test('calendar starts on Monday and includes every leap-February date', () => {
  const days = monthDays('2028-02');
  assert.equal(days.length, 42);
  assert.equal(new Date(`${days[0].value}T00:00:00Z`).getUTCDay(), 1);
  assert.equal(days.filter(x => x.current).length, 29);
  assert.ok(days.some(x => x.value === '2028-02-29'));
});
test('calendar shifts years correctly without local timezone drift', () => {
  assert.equal(shiftMonth('2026-12', 1), '2027-01');
  assert.equal(shiftMonth('2027-01', -1), '2026-12');
});
test('SSE parses multiple events and ignores comment heartbeat frames', () => {
  const result = parseSSE(': keepalive\n\nevent: revision\ndata: {"revision":7}\n\nevent: heartbeat\ndata: {"time":"now"}\n\n');
  assert.deepEqual(result.events.map(x => x.type), ['revision', 'heartbeat']);
  assert.equal(JSON.parse(result.events[0].data).revision, 7);
  assert.equal(result.rest, '');
});
test('SSE preserves incomplete packets across chunks including CRLF boundaries', () => {
  const first = parseSSE('event: revision\r\ndata: {"revision":1}\r');
  assert.equal(first.events.length, 0);
  const second = parseSSE(first.rest + '\n\r\n');
  assert.equal(second.events.length, 1);
  assert.equal(JSON.parse(second.events[0].data).revision, 1);
});
test('SSE multiline data joins exactly as required', () => {
  assert.equal(parseSSE('data: first\ndata: second\n\n').events[0].data, 'first\nsecond');
});
test('400 field errors map metadata Russian labels to actual field names', () => {
  assert.deepEqual(fieldErrors({ status: 400, message: 'Некорректное поле: Инвентарный номер' }, [{ name: 'InventoryNumber', label: 'Инвентарный номер' }, { name: 'Name', label: 'Наименование' }]), { InventoryNumber: 'Некорректное поле: Инвентарный номер' });
});
test('structured API field feedback is retained; non-validation failures are not mislabeled', () => {
  assert.deepEqual(fieldErrors({ status: 400, details: { fields: { Name: 'Обязательно' } } }, []), { Name: 'Обязательно' });
  assert.deepEqual(fieldErrors({ status: 409, message: 'Name конфликт' }, [{ name: 'Name' }]), {});
});
