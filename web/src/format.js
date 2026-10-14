export const number = (value, digits = 0) => new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(Number(value) || 0);
export const date = value => {
  if (!value) return '—';
  const time = new Date(value.length === 10 ? `${value}T00:00:00` : value.replace(/Z$/, '') + 'Z');
  return Number.isNaN(time.getTime()) ? value : new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', ...(value.length > 10 ? { timeStyle: 'short' } : {}) }).format(time);
};
export const badge = value => {
  const text = String(value || '').toLowerCase();
  if (/выполн|закрыт|в работе|актив|низкий/.test(text)) return 'success';
  if (/ремонт|ожида|назнач|высок|средн|планир/.test(text)) return 'warning';
  if (/просроч|критич|вывед|отмен|просто/.test(text)) return 'danger';
  return 'neutral';
};
export const utcInput = () => new Date().toISOString().slice(0, 19);
export const readable = key => ({ Id: 'ID', Name: 'Наименование', Number: 'Заявка', Status: 'Статус', EquipmentName: 'Оборудование', InventoryNumber: 'Инв. номер', WorkshopName: 'Цех', TeamName: 'Бригада', Priority: 'Приоритет', PlannedAt: 'Плановая дата', CreatedAt: 'Создано', MaterialName: 'Материал', Stock: 'Остаток', MinimumStock: 'Мин. остаток', Quantity: 'Количество', UnitPrice: 'Цена', ActualStart: 'Начало работ', ActualEnd: 'Окончание работ', PlannedStart: 'Плановое начало', PlannedEnd: 'Плановое окончание', NewStatus: 'Новый статус', OldStatus: 'Предыдущий статус', ChangedAt: 'Изменено', ChangedBy: 'Пользователь', Email: 'Email', Phone: 'Телефон', IsActive: 'Активен', Code: 'Код', Model: 'Модель', RoleCode: 'Роль', Unit: 'Ед. изм.', Specialization: 'Специализация', Description: 'Описание', metrics: 'Основные показатели', equipment: 'Единиц оборудования', open_orders: 'Открытые заявки', overdue: 'Просроченные заявки', low_stock: 'Материалы с низким остатком', downtime_hours: 'Простой, ч', equipment_status: 'Оборудование по статусам', orders_by_status: 'Заявки по статусам', by_workshop: 'Оборудование по цехам', label: 'Показатель', value: 'Количество', period: 'Расчётный период', from: 'Начало периода', to: 'Конец периода' })[key] || key;
