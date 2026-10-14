-- Учебные данные по Приложению 6: 15 единиц, 3 цеха, 3 бригады,
-- 6 видов ТО, 36 нормативов, 10 материалов и 18 записей графика 2027 года.
-- Статус «Активен» нормализован в «в работе» по требованиям Приложения 5.
-- НЕТ паролей, хешей, пользователей и заявок: пользователей создаёт backend setup.
-- Цены и поставщик не даны в источнике: ниже открыто обозначенные учебные допущения.
-- StartedOn принят равным CommissionedOn; модель используется как тип, где есть норматив.
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET NUMERIC_ROUNDABORT OFF;
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF OBJECT_ID(N'dbo.WorkOrders',N'U') IS NULL THROW 51002,N'Сначала выполните схему.',1;
IF EXISTS (SELECT 1 FROM dbo.Roles) OR EXISTS (SELECT 1 FROM dbo.Equipment)
    THROW 51003,N'Начальные данные уже существуют. Повторное заполнение не выполняется.',1;
BEGIN TRANSACTION;
INSERT dbo.Roles(Code,Name) VALUES
    ('admin',N'Администратор'),('engineer',N'Инженер по ТОиР'),
    ('master',N'Мастер цеха'),('member',N'Член ремонтной бригады'),('manager',N'Руководитель');
INSERT dbo.Workshops(Code,Name) VALUES
    (N'МСЦ',N'Механосборочный цех'),(N'СТЦ',N'Сварочно-термический цех'),(N'ЭТЦ',N'Электротехнический цех');
INSERT dbo.Teams(Code,Name,Specialization,WorkshopId)
SELECT v.Code,v.Name,v.Specialization,w.Id FROM (VALUES
    (N'BR-1',N'Бригада №1',N'Механики-ремонтники',N'МСЦ'),
    (N'BR-2',N'Бригада №2',N'Электрики-сварщики',N'СТЦ'),
    (N'BR-3',N'Бригада №3',N'Электромонтёры-схемщики',N'ЭТЦ')
) v(Code,Name,Specialization,WorkshopCode) JOIN dbo.Workshops w ON w.Code=v.WorkshopCode;
INSERT dbo.EquipmentTypes(Code,Name) VALUES
    (N'LATHE',N'Токарный станок'),(N'MILL',N'Фрезерный станок'),
    (N'WELDER',N'Сварочный автомат'),(N'FURNACE',N'Печь муфельная'),
    (N'TRANSFORMER',N'Трансформатор'),(N'MOTOR',N'Электродвигатель');
INSERT dbo.Equipment(InventoryNumber,Name,Model,WorkshopId,EquipmentTypeId,CommissionedOn,StartedOn,Status)
SELECT v.Code,v.Name,v.Model,w.Id,t.Id,v.StartedOn,v.StartedOn,v.Status
FROM (VALUES
    (N'EQ-001',N'Токарно-винторезный станок',N'16К20',N'МСЦ',N'LATHE','20180315',N'в работе'),
    (N'EQ-002',N'Вертикально-фрезерный станок',N'6Р13Ф3',N'МСЦ',N'MILL','20190720',N'в работе'),
    (N'EQ-003',N'Горизонтально-расточной станок',N'2М614',N'МСЦ',NULL,'20171110',N'в работе'),
    (N'EQ-004',N'Круглошлифовальный станок',N'3У131М',N'МСЦ',NULL,'20200405',N'в работе'),
    (N'EQ-005',N'Координатно-расточной станок',N'2Е450',N'МСЦ',NULL,'20160912',N'в ремонте'),
    (N'EQ-006',N'Сварочный автомат',N'АДФ-1000',N'СТЦ',N'WELDER','20190202',N'в работе'),
    (N'EQ-007',N'Полуавтомат сварочный',N'ПДГ-500',N'СТЦ',NULL,'20200515',N'в работе'),
    (N'EQ-008',N'Печь муфельная',N'СНОЛ-1,6.2,5.2,5/9',N'СТЦ',N'FURNACE','20180810',N'в работе'),
    (N'EQ-009',N'Установка ТВЧ-закалки',N'УЗТ-100',N'СТЦ',NULL,'20171120',N'в простое'),
    (N'EQ-010',N'Сварочный выпрямитель',N'ВДУ-506',N'СТЦ',NULL,'20210905',N'в работе'),
    (N'EQ-011',N'Трансформатор силовой',N'ТМ-400/10',N'ЭТЦ',N'TRANSFORMER','20160115',N'в работе'),
    (N'EQ-012',N'Частотный преобразователь',N'АИР-132М4',N'ЭТЦ',NULL,'20190820',N'в работе'),
    (N'EQ-013',N'Электродвигатель асинхронный',N'4А250М4У3',N'ЭТЦ',N'MOTOR','20200310',N'в работе'),
    (N'EQ-014',N'Высоковольтный вводной шкаф',N'ЯКНО-10',N'ЭТЦ',NULL,'20181105',N'в ремонте'),
    (N'EQ-015',N'Система управления конвейером',N'SCADA-2000',N'ЭТЦ',NULL,'20211212',N'в работе')
) v(Code,Name,Model,WorkshopCode,TypeCode,StartedOn,Status)
JOIN dbo.Workshops w ON w.Code=v.WorkshopCode LEFT JOIN dbo.EquipmentTypes t ON t.Code=v.TypeCode;
-- PlannedHours — базовое значение; точный диапазон для модели в MaintenanceNorms.
INSERT dbo.MaintenanceTypes(Code,Name,Description,IntervalKind,IntervalDays,PlannedHours,RequiresStop) VALUES
    (N'TO-1',N'Ежемесячное ТО',N'Осмотр, крепления, смазка, контроль температуры и вибрации.','days',30,4,1),
    (N'TO-2',N'Квартальное ТО',N'Углублённая диагностика, замеры и замена изнашиваемых деталей.','days',90,8,1),
    (N'TO-3',N'Полугодовое ТО',N'Частичная разборка, дефектовка, ремонт и калибровка.','days',180,16,1),
    (N'TO-4',N'Годовое ТО',N'Полная разборка, замена изношенных деталей и испытания.','days',365,32,1),
    (N'TP',N'Текущий ремонт',N'Устранение внезапных отказов и восстановление работоспособности.','condition',NULL,8,1),
    (N'KR',N'Капитальный ремонт',N'Восстановление ресурса и модернизация по решению главного инженера.','condition',NULL,120,1);
INSERT dbo.MaintenanceNorms(EquipmentTypeId,MaintenanceTypeId,MinimumHours,MaximumHours)
SELECT t.Id,m.Id,v.MinHours,v.MaxHours FROM (VALUES
    (N'LATHE',N'TO-1',4,4),(N'LATHE',N'TO-2',8,8),(N'LATHE',N'TO-3',16,16),
    (N'LATHE',N'TO-4',32,32),(N'LATHE',N'TP',8,24),(N'LATHE',N'KR',120,120),
    (N'MILL',N'TO-1',4,4),(N'MILL',N'TO-2',8,8),(N'MILL',N'TO-3',16,16),
    (N'MILL',N'TO-4',32,32),(N'MILL',N'TP',8,24),(N'MILL',N'KR',120,120),
    (N'WELDER',N'TO-1',3,3),(N'WELDER',N'TO-2',6,6),(N'WELDER',N'TO-3',12,12),
    (N'WELDER',N'TO-4',24,24),(N'WELDER',N'TP',6,16),(N'WELDER',N'KR',80,80),
    (N'FURNACE',N'TO-1',2,2),(N'FURNACE',N'TO-2',5,5),(N'FURNACE',N'TO-3',10,10),
    (N'FURNACE',N'TO-4',20,20),(N'FURNACE',N'TP',4,12),(N'FURNACE',N'KR',60,60),
    (N'TRANSFORMER',N'TO-1',3,3),(N'TRANSFORMER',N'TO-2',6,6),(N'TRANSFORMER',N'TO-3',12,12),
    (N'TRANSFORMER',N'TO-4',24,24),(N'TRANSFORMER',N'TP',8,16),(N'TRANSFORMER',N'KR',72,72),
    (N'MOTOR',N'TO-1',2,2),(N'MOTOR',N'TO-2',4,4),(N'MOTOR',N'TO-3',8,8),
    (N'MOTOR',N'TO-4',16,16),(N'MOTOR',N'TP',4,12),(N'MOTOR',N'KR',48,48)
) v(TypeCode,MaintenanceCode,MinHours,MaxHours)
JOIN dbo.EquipmentTypes t ON t.Code=v.TypeCode JOIN dbo.MaintenanceTypes m ON m.Code=v.MaintenanceCode;
INSERT dbo.Suppliers(Name) VALUES(N'Учебный поставщик — заменить реальными данными');
INSERT dbo.Materials(Code,Name,Unit,Stock,MinimumStock,Location,UnitPrice,SupplierId)
SELECT v.Code,v.Name,v.Unit,v.Stock,v.MinimumStock,v.Location,v.Price,s.Id
FROM (VALUES
    (N'М-001',N'Масло индустриальное И-20',N'л',200,50,N'Склад №3',150.00),
    (N'М-002',N'Смазка Литол-24',N'кг',80,20,N'Склад №3',450.00),
    (N'М-003',N'Фильтр масляный (16К20)',N'шт',15,5,N'Склад №1',850.00),
    (N'М-004',N'Ремень приводной (6Р13Ф3)',N'шт',10,3,N'Склад №1',1200.00),
    (N'М-005',N'Подшипник 6-205',N'шт',50,15,N'Склад №2',600.00),
    (N'М-006',N'Электрод сварочный МР-3',N'кг',300,100,N'Склад №4',220.00),
    (N'М-007',N'Провод ПВС 3х2,5',N'м',500,100,N'Склад №2',180.00),
    (N'М-008',N'Термопара ТХК',N'шт',20,5,N'Склад №2',2500.00),
    (N'М-009',N'Масло трансформаторное',N'л',150,50,N'Склад №3',200.00),
    (N'М-010',N'Изолента ПВХ',N'рул',30,10,N'Склад №2',80.00)
) v(Code,Name,Unit,Stock,MinimumStock,Location,Price)
CROSS JOIN dbo.Suppliers s WHERE s.Name=N'Учебный поставщик — заменить реальными данными';
INSERT dbo.MaintenanceSchedule(EquipmentId,MaintenanceTypeId,PlannedAt,Status,TeamId)
SELECT e.Id,m.Id,CONVERT(datetime2(0),v.PlannedDate),N'назначено',t.Id FROM (VALUES
    (N'EQ-001',N'TO-2','20270120',N'BR-1'),(N'EQ-002',N'TO-1','20270125',N'BR-1'),
    (N'EQ-006',N'TO-1','20270205',N'BR-2'),(N'EQ-008',N'TO-2','20270215',N'BR-2'),
    (N'EQ-001',N'TO-1','20270310',N'BR-1'),(N'EQ-011',N'TO-1','20270320',N'BR-3'),
    (N'EQ-013',N'TO-2','20270325',N'BR-3'),(N'EQ-003',N'TO-2','20270405',N'BR-1'),
    (N'EQ-010',N'TO-1','20270415',N'BR-2'),(N'EQ-001',N'TO-3','20270510',N'BR-1'),
    (N'EQ-008',N'TO-1','20270520',N'BR-2'),(N'EQ-011',N'TO-2','20270605',N'BR-3'),
    (N'EQ-002',N'TO-2','20270710',N'BR-1'),(N'EQ-006',N'TO-2','20270815',N'BR-2'),
    (N'EQ-001',N'TO-1','20270910',N'BR-1'),(N'EQ-008',N'TO-3','20271005',N'BR-2'),
    (N'EQ-011',N'TO-3','20271110',N'BR-3'),(N'EQ-001',N'TO-4','20271215',N'BR-1')
) v(EquipmentCode,MaintenanceCode,PlannedDate,TeamCode)
JOIN dbo.Equipment e ON e.InventoryNumber=v.EquipmentCode
JOIN dbo.MaintenanceTypes m ON m.Code=v.MaintenanceCode JOIN dbo.Teams t ON t.Code=v.TeamCode;
COMMIT TRANSACTION;
SELECT (SELECT COUNT(*) FROM dbo.Equipment) AS EquipmentCount,
    (SELECT COUNT(*) FROM dbo.MaintenanceSchedule) AS ScheduleCount,
    (SELECT COUNT(*) FROM dbo.Materials) AS MaterialsCount;
