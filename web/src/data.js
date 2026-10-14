// Pure helpers shared by charts, filters, exports and regression tests.
export function csvText(rows, columns) {
  const cell = value => {
    let text = String(value ?? '');
    // Prevent spreadsheet formula injection in user-entered labels.
    if (typeof value === 'string' && /^[=+@\-\t\r]/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  };
  return '\ufeff' + [columns.map(c => c.label), ...rows.map(row => columns.map(c => row[c.key]))]
    .map(row => row.map(cell).join(';')).join('\r\n');
}
export function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = name; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function tableRows(rows, search, key, direction = 'asc') {
  const needle = String(search || '').toLocaleLowerCase('ru-RU');
  const result = rows.filter(row => Object.values(row).some(v => String(v ?? '').toLocaleLowerCase('ru-RU').includes(needle)));
  if (!key) return result;
  return result.sort((a, b) => {
    const x = a[key], y = b[key];
    const value = typeof x === 'number' && typeof y === 'number' ? x - y : String(x ?? '').localeCompare(String(y ?? ''), 'ru', { numeric: true });
    return direction === 'desc' ? -value : value;
  });
}
export function filterQuery(filters) {
  return Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== '' && v != null && (!Array.isArray(v) || v.length)).map(([key, value]) => [key, Array.isArray(value) ? value.join(',') : value]));
}
export function monthDays(month) {
  const [year, index] = month.split('-').map(Number);
  const start = new Date(Date.UTC(year, index - 1, 1));
  const offset = (start.getUTCDay() + 6) % 7;
  return Array.from({ length: 42 }, (_, i) => {
    const value = new Date(Date.UTC(year, index - 1, i - offset + 1)).toISOString().slice(0, 10);
    return { value, day: Number(value.slice(-2)), current: value.startsWith(month) };
  });
}
export function shiftMonth(month, delta) {
  const [year, index] = month.split('-').map(Number);
  return new Date(Date.UTC(year, index - 1 + delta, 1)).toISOString().slice(0, 7);
}
export function parseSSE(buffer) {
  const normalized = buffer.replaceAll('\r\n', '\n');
  const blocks = normalized.split('\n\n');
  const rest = blocks.pop();
  const events = blocks.map(block => {
    const event = { type: 'message', data: '' };
    const data = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event.type = line.slice(6).trim();
      if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
    }
    event.data = data.join('\n');
    return event;
  }).filter(event => event.data);
  return { events, rest };
}
export function fieldErrors(error, fields) {
  if (error?.status !== 400) return {};
  const result = {};
  const structured = error.details?.fields || error.details?.errors || {};
  if (!Array.isArray(structured)) for (const [key, value] of Object.entries(structured)) result[key] = String(value);
  for (const field of fields) {
    if (error.message?.includes(field.name) || error.message?.toLowerCase().includes(field.label?.toLowerCase())) result[field.name] = error.message;
  }
  return result;
}
