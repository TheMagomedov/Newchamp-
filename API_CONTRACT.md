# ТОиР-Проф: контракт API

Адрес: http://127.0.0.1:8000/api. Отдельная QA-копия — порт 8010. OpenAPI: /docs.
JSON: {success,data,message,error_code}. Кроме login/refresh/health нужен Authorization: Bearer.
Записи — PascalCase, агрегаты — snake_case. SQL хранит UTC без смещения. Расчёты стоимости через Decimal, сериализация — JSON numbers.

## Авторизация и права

- POST /auth/login {email,password} → {access_token,refresh_token,expires_in,user}.
- POST /auth/refresh {refresh_token} → ротация пары. Старый access связан со старой сессией и перестаёт работать.
- POST /auth/logout {refresh_token} → отзыв сессии. GET /auth/me → пользователь.
- User: {Id,Email,Name,Role,WorkshopId,TeamId}; роли admin,engineer,master,member,manager.
- Мастер видит оборудование/заявки/график своего цеха; участник — заявки своей бригады и связанное оборудование. Manager только читает.
- Ограничения области действуют в деталях, поиске, аналитике, уведомлениях, SSE и экспорте.
- Склад общий. Инженер не списывает материалы. Credentials не возвращаются в ресурсах/событиях.

## Метаданные и CRUD

- GET /meta → {resources:[{key,label,canWrite,canDelete,fields:[{name,label,type,required,readOnly,options,lookup}]}],statuses}.
- GET /lookups → ресурс: [{id,label}]. Equipment дополнительно содержит workshop_id. Masters: [{id,label,workshop_id}], только активные доступные мастера. MasterId в метаданных ссылается на masters.
- Ресурсы: equipment,work-orders,schedule,materials,teams,maintenance-types,workshops,suppliers,equipment-types,users. Users только admin.
- GET /{resource} → {items,total,page,page_size}. Фильтры: search,status,workshop_id,workshop_ids=1,2,equipment_id,team_id,priority,type,from,to,date_from,date_to. Пагинация page=1,page_size=25 (максимум 100). Сортировка sort_by=Id,sort_dir=asc|desc; одинаковые значения упорядочиваются по Id.
- Equipment: model (подстрока); materials: location (подстрока). Неизвестные/секретные поля сортировки отклоняются.
- Даты списка относятся к PlannedAt у schedule, CreatedAt у work-orders/equipment. Для оборудования даты означают регистрацию, не простой.
- GET /{resource}/{id} → запись. POST →201, PUT /{resource}/{id}, DELETE /{resource}/{id} → результат.
- Users принимает Password, не PasswordHash. При изменении можно не задавать пароль.
- Equipment удаляется мягко и исчезает из новых списков/lookup; активные связи запрещают удаление. API физически удаляет только заявки в статусе создана.
- Stock нельзя уменьшить общей формой: требуется списание в заявке. Пополнение разрешено.
- Number сохраняет прежний формат БД. DisplayNumber — Z-2026-0001 (минимум 4 цифры, большие номера не обрезаются). Поиск понимает DisplayNumber и суффикс с ведущими нулями. Перенумерации существующих заявок нет.

## Детали и история

- GET /equipment/{id}, /equipment/{id}/details: поля equipment плюс orders,schedule,history.
- GET /equipment/{id}/related → {orders,schedule,history}.
- GET /work-orders/{id}: поля заявки плюс materials,history.
- GET /teams/{id}: поля бригады плюс members,active_orders,workload:{active,planned_hours}. Members содержит только контактные поля.
- GET /equipment/{id}/history и /work-orders/{id}/history: массив истории, новые записи первыми.

## Заявки и график

- POST /work-orders/{id}/transition {status,team_id?,actual_start?,actual_end?,completion_report?}.
- Цикл: создана → назначена → в работе ↔ ожидает материалов → выполнена → закрыта. Из ожидания перед завершением требуется возобновление. Отмена — до начала работ.
- GET /work-orders/{id}/materials → [{WorkOrderId,MaterialId,MaterialName,Unit,Quantity,UnitPrice,...}].
- POST /work-orders/{id}/materials {MaterialId,Quantity,Comment?}; PUT /work-orders/{id}/materials/{materialId} {Quantity,Comment?}; DELETE по тому же пути. Цена фиксируется сервером.
- POST /work-orders/{id}/complete {completion_report,actual_end?,materials?:[{MaterialId,Quantity,Comment?}]} сохраняет отчёт, новые списания и завершение одной транзакцией. Нехватка материала откатывает всё. Существующий MaterialId в complete не перезаписывается: используйте отдельный PUT строки. Инженеру запрещён непустой materials.
- Фактический конец строго позже начала. При мгновенном завершении подождите секунду либо укажите правильное фактическое время. Complete отклоняет будущий фактический конец.
- GET /schedule поддерживает upcoming_days=7, overdue=true; IsOverdue вычисляется сервером.
- GET /schedule/upcoming?days=7&workshop_id=&equipment_id= и /schedule/overdue → {items,total}. Просрочка определяется по времени, без фоновой переписи статуса.
- POST /schedule/{id}/create-order {master_id,planned_hours?,planned_start?,priority?,team_id?} → заявка с ScheduleOrderReused.
- Master_id обязателен: активный мастер цеха оборудования, мастер создаёт от себя. Дата/бригада берутся из графика; длительность — минимум норматива EquipmentType/MaintenanceType, иначе PlannedHours вида ТО. Прошедший график требует новой planned_start.
- SQL-блокировка по записи графика и уникальный ScheduleId гарантируют одну заявку даже с разными ключами идемпотентности. При известной бригаде заявка сразу назначается; пересечения её периодов проверяет SQL.

## Аналитика и даты

GET /analytics/dashboard (алиасы /analytics,/dashboard,/analytics/dashboard-summary):
from,to,workshop_id,workshop_ids,type,priority,equipment_id.

По умолчанию последние 30 суток. To=2026-10-13 включает весь день UTC; timestamp to — исключающая граница. Смещение ISO8601 переводится в UTC. Максимум 10 лет. Предыдущий период — непосредственно предшествующий интервал той же длины.

- Metrics: equipment,repair_equipment,open_orders,overdue,low_stock,downtime_hours,today_orders,avg_completion_hours,completed_orders,material_cost.
- Первые 5 — текущее состояние доступной области, не исторический снимок. Today_orders — сегодня UTC. Простой, среднее время, выполненные и стоимость — заданный период.
- Trends: downtime_hours,completed_orders,material_cost,avg_completion_hours → {current,previous,delta,percent,available,reason?}. Нулевой предыдущий знаменатель даёт percent=null; отсутствующее среднее — null.
- Kpi_trends для снимков имеют available=false: исторические снимки не сохранялись, дельта не выдумывается.
- Equipment_status,orders_by_status,orders_by_type,orders_by_priority,by_workshop → [{label,value}].
- Orders_by_workshop → [{workshop_id,label,value}].
- Orders_daily → [{date,created,completed}], downtime_daily → [{date,hours}], materials_daily → [{date,cost}]. Максимум последние 30 календарных дней периода; начало в period.timeline_from.
- Top_downtime → первые 10 {equipment_id,inventory_number,label,workshop_id,hours}; downtime_all — весь список.
- Materials_top → первые 10 {material_id,code,label,unit,quantity,cost}; materials_all — весь список. Стоимость использует историческую цену списания.
- Schedule → {planned,completed,on_time,overdue,due,adherence_percent,trend,by_workshop:[{workshop_id,label,...показатели}]}.
- Отменённые ТО исключены. Наступившие — PlannedAt < сейчас. В срок — завершённая связанная заявка с ActualEnd <= PlannedEnd. Нет наступивших ТО: процентnull. Priority оставляет график, связанный с заявками этого приоритета.
- Team_rankings → [{team_id,label,completed,active,avg_completion_hours,on_time_percent,planned_hours}], сортировка по выполненным, затем своевременности.
- Recent_orders:10 последних созданных в периоде; active_orders:до 10 текущих по ближайшему окончанию; upcoming:до 10 ТО ближайших 7 дней; low_stock:до 20 позиций с остатком <= минимум.
- Period:{from,to,timeline_from,previous_from,previous_to}, calculated_at.

Простой — сумма пересечений фактических интервалов заявок в работе/ожидании/выполненных/закрытых с периодом; открытый конец ограничен сейчас. Пересекающиеся заявки суммируются, не объединяются: это часы по заявкам, не уникальные машино-часы.

GET /analytics/downtime-dynamics → {items,top_equipment,period}; /analytics/team-efficiency → {items}; /reports/summary → полная сводка. Фильтры аналогичны.

## Отчёты

- GET /reports/preview?type=... → {type,title,columns:[{key,label}],rows,summary,charts?}.
- Типы: equipment,work-orders,materials,downtime,schedule,team-efficiency,material-usage,analytics; технический orders — динамика по дням.
- Charts: [{title,unit,mode?:bar|line,items:[{label,value}]}].
- POST /reports/export принимает те же параметры плюс format:pdf|xlsx|csv → {url,expires_in:15,filename}.
- Фильтры: from,to,workshop_id,workshop_ids,equipment_id,priority,order_type. Здесь type — вид отчёта, order_type — тип заявки.
- Type=analytics: block=all|orders|downtime|materials|schedule|teams.
- Реестры equipment/materials отражают текущее состояние; даты применяются к заявкам и периодным отчётам. Экспорт аналитики использует полные списки, не TOP10; дневные ряды ограничены 30 днями как в интерфейсе.
- PDF: период, фильтры, таблицы, номера страниц, диаграммы по той же выборке. Это печатный отчёт, не пиксельная копия браузера. CSV/XLSX — таблицы, формулы в пользовательском тексте экранируются.
- GET /download/{token} требует Bearer владельца. После 15 секунд 410 (при предварительной очистке кеша 404); чужой пользователь 404. Ссылки в памяти процесса, перезапуск их удаляет.

## Импорт, поиск, уведомления, SSE

- POST /import/equipment?filename=file.csv: raw CSV UTF-8 или XLSX, только admin/engineer, максимум 2 МБ/10000 строк, проверка распакованного размера. Ответ {inserted}. Импорт атомарный.
- GET /search?q=&limit=20 (алиас /global-search) → {items:[{resource,id,label,subtitle}],total}. Ищет equipment/work-orders/materials/teams/schedule; admin также пользователей. ФИО мастера находит только доступные заявки этого мастера.
- GET /notifications → {items:[{id,kind,severity,title,message,resource,entity_id}],total}: просроченные заявки, неназначенные, просроченный график, низкий склад.
- Прочитанность хранит клиент локально. Серверной постоянной таблицы/read endpoint нет.
- GET /events: SSE через fetch с Bearer-заголовком, без токенов в URL. Первое event:revision содержит {revision,changed_resources}; далее revision только при изменении видимой области.
- SQL проверяется каждые 2 секунды по количеству/ID/аудиту; heartbeat примерно 15 секунд с time. Отзыв/истечение сессии даёт auth_expired и закрывает поток.
- Событие — сигнал повторно запросить раздел, не полный объект. Наступление временной просрочки не пишет аудит: уведомления также обновляйте периодически/на heartbeat.

## Надёжность и ограничения

Мутации: Idempotency-Key UUID, результат хранится в SQL для пользователя/метода/пути/тела; иное тело с тем же ключом 409. PUT заявки может передать _version (hex Version) для обнаружения конкурентного изменения.

Ошибки 400/401/403/404/409/410/429, объяснение в message. Лимит 100 запросов пользователя/мин, login20 попыток/IP/мин. При ошибке форму не очищать.

GET /health проверяет SQL. GET /integrations/1c/status честно возвращает stub/connected=false. Реального обмена 1 С нет.

Учебный график поставки относится к 2027 году: раньше этого периода исторические графики закономерно пусты. API не подменяет их синтетическими показателями. Для обучения завершённому циклу создавайте отдельные учебные заявки.

Обновление не пересоздаёт таблицы и не изменяет учебные данные. 39 SQL selftests остаются совместимыми. Интеграционные pytest допускают только ChampTraining_ и очищают только собственные случайные fixture ID.
