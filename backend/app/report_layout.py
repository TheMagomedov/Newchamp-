"""Колонки и русские подписи отчётов; общие для просмотра и экспорта."""
REPORT_COLUMNS={
 'equipment':['InventoryNumber','Name','WorkshopName','Status','Model','CommissionedOn'],
 'work-orders':['DisplayNumber','EquipmentName','Type','Status','Priority','PlannedStart','PlannedEnd'],
 'materials':['Code','Name','Unit','Stock','MinimumStock','UnitPrice'],
 'downtime':['inventory_number','label','workshop_id','hours'],
 'schedule':['workshop_id','label','planned','completed','on_time','overdue','adherence_percent'],
 'team-efficiency':['label','completed','active','avg_completion_hours','on_time_percent','planned_hours'],
 'material-usage':['code','label','unit','quantity','cost'],
 'analytics':['section','label','value','unit','detail'],
 'orders':['date','created','completed'],
}
REPORT_LABELS={
 'inventory_number':'Инвентарный номер','label':'Наименование','workshop_id':'Цех ID','hours':'Простой, ч',
 'planned':'План ТО','completed':'Выполнено','on_time':'В срок','overdue':'Просрочено','adherence_percent':'Соблюдение плана, %',
 'active':'Активные заявки','avg_completion_hours':'Среднее время, ч','on_time_percent':'В срок, %','planned_hours':'Плановая загрузка, ч',
 'code':'Код','unit':'Единица','quantity':'Расход','cost':'Стоимость','section':'Раздел','value':'Значение','detail':'Дополнительно',
 'date':'Дата UTC','created':'Создано',
 'DisplayNumber':'Номер',
}
REPORT_TITLES={'equipment':'Реестр оборудования','work-orders':'Реестр заявок','materials':'Остатки материалов',
 'downtime':'Простои оборудования','schedule':'Выполнение графика ТО','team-efficiency':'Эффективность бригад',
 'material-usage':'Расход материалов','analytics':'Аналитический отчёт','orders':'Динамика заявок'}
