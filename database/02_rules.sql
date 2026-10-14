-- SQL Server 2022+. Выполнить после 01_schema.sql в той же учебной БД.
-- Приложение задаёт EXEC sys.sp_set_session_context N'ActorId', @UserId
-- для КАЖДОГО взятого из пула соединения; NULL означает системную операцию.
-- SESSION_CONTEXT обеспечивает атрибуцию, но не заменяет авторизацию API.
-- Даты datetime2 в UTC; интервалы [начало, конец), без производственного календаря.
-- Простой суммируется по заявкам, включая уже закрытые; пересечения суммируются.
-- При удалении/уменьшении строки списания запас возвращается на склад.
-- История цены неизменна; при новом списании берётся текущая цена материала.
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET NUMERIC_ROUNDABORT OFF;
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF OBJECT_ID(N'dbo.WorkOrders',N'U') IS NULL
    THROW 51002, N'Сначала выполните 01_schema.sql в выбранной БД.', 1;
GO
CREATE OR ALTER TRIGGER dbo.TR_Users_Scope ON dbo.Users AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM inserted i JOIN dbo.Roles r ON r.Id=i.RoleId
        WHERE (r.Code='master' AND i.WorkshopId IS NULL)
           OR (r.Code='member' AND i.TeamId IS NULL))
        THROW 51040, N'Мастеру нужен цех, участнику бригады — бригада.', 1;
END;
GO
CREATE OR ALTER TRIGGER dbo.TR_Users_SoftDelete ON dbo.Users INSTEAD OF DELETE
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE u SET IsActive=0 FROM dbo.Users u JOIN deleted d ON d.Id=u.Id;
    UPDATE t SET RevokedAt=SYSUTCDATETIME() FROM dbo.RefreshTokens t
        JOIN deleted d ON d.Id=t.UserId WHERE t.RevokedAt IS NULL;
END;
GO
CREATE OR ALTER TRIGGER dbo.TR_Equipment_Rules ON dbo.Equipment AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;
    IF TRIGGER_NESTLEVEL(OBJECT_ID(N'dbo.TR_Equipment_Rules')) > 1 RETURN;
    DECLARE @Actor int=TRY_CONVERT(int,SESSION_CONTEXT(N'ActorId'));
    IF EXISTS (SELECT 1 FROM inserted i JOIN deleted d ON d.Id=i.Id
        WHERE d.Status=N'выведено из эксплуатации' AND i.Status<>d.Status)
        THROW 51010, N'Возврат списанного оборудования в работу запрещён.', 1;
    IF EXISTS (SELECT 1 FROM inserted WHERE StartedOn>CONVERT(date,SYSUTCDATETIME()))
        THROW 51011, N'Дата ввода в работу не может быть в будущем.', 1;
    IF EXISTS (SELECT 1 FROM inserted i WHERE i.IsDeleted=1 AND
        (EXISTS (SELECT 1 FROM dbo.WorkOrders w WHERE w.EquipmentId=i.Id
            AND w.Status NOT IN (N'закрыта',N'отменена'))
        OR EXISTS (SELECT 1 FROM dbo.MaintenanceSchedule s WHERE s.EquipmentId=i.Id
            AND s.Status<>N'отменено')))
        THROW 51012, N'Для удаления завершите заявки и отмените записи графика.', 1;
    UPDATE e SET UpdatedAt=SYSUTCDATETIME(),UpdatedBy=@Actor,
        CreatedBy=CASE WHEN d.Id IS NULL THEN COALESCE(i.CreatedBy,@Actor) ELSE e.CreatedBy END
    FROM dbo.Equipment e JOIN inserted i ON i.Id=e.Id LEFT JOIN deleted d ON d.Id=i.Id;
    INSERT dbo.EquipmentStatusHistory(EquipmentId,InventoryNumber,OldStatus,NewStatus,ChangedBy)
    SELECT i.Id,i.InventoryNumber,d.Status,i.Status,@Actor
    FROM inserted i LEFT JOIN deleted d ON d.Id=i.Id
    WHERE d.Id IS NULL OR d.Status<>i.Status;
    INSERT dbo.AuditLog(ActorId,Entity,EntityId,Action,OldData,NewData)
    SELECT @Actor,N'Equipment',CONVERT(nvarchar(80),COALESCE(i.Id,d.Id)),
        CASE WHEN d.Id IS NULL THEN N'CREATE' WHEN i.Id IS NULL THEN N'DELETE' ELSE N'UPDATE' END,
        CASE WHEN d.Id IS NOT NULL THEN (SELECT d.* FOR JSON PATH,WITHOUT_ARRAY_WRAPPER) END,
        CASE WHEN i.Id IS NOT NULL THEN (SELECT i.* FOR JSON PATH,WITHOUT_ARRAY_WRAPPER) END
    FROM inserted i FULL JOIN deleted d ON d.Id=i.Id;
END;
GO
CREATE OR ALTER TRIGGER dbo.TR_MaintenanceTypes_Active ON dbo.MaintenanceTypes AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM inserted i JOIN deleted d ON d.Id=i.Id
        JOIN dbo.MaintenanceSchedule s ON s.MaintenanceTypeId=i.Id
        WHERE i.IsActive=0 AND d.IsActive=1 AND s.Status NOT IN (N'выполнено',N'отменено'))
        THROW 51041, N'Нельзя отключить вид ТО с незавершённым графиком.', 1;
END;
GO
CREATE OR ALTER TRIGGER dbo.TR_Schedule_Rules ON dbo.MaintenanceSchedule AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM inserted i JOIN dbo.Equipment e ON e.Id=i.EquipmentId
        JOIN dbo.MaintenanceTypes m ON m.Id=i.MaintenanceTypeId
        WHERE i.Status NOT IN (N'выполнено',N'отменено') AND
            (e.IsDeleted=1 OR e.Status=N'выведено из эксплуатации' OR m.IsActive=0))
        THROW 51042, N'В графике требуется действующее оборудование и активный вид ТО.', 1;
    IF EXISTS (SELECT 1 FROM inserted i JOIN dbo.WorkOrders w ON w.ScheduleId=i.Id
        WHERE w.EquipmentId<>i.EquipmentId OR w.MaintenanceTypeId IS NULL
            OR w.MaintenanceTypeId<>i.MaintenanceTypeId)
        THROW 51024, N'Оборудование и вид ТО графика должны совпадать с заявкой.', 1;
END;
GO
CREATE OR ALTER TRIGGER dbo.TR_WorkOrders_Rules ON dbo.WorkOrders AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Actor int=TRY_CONVERT(int,SESSION_CONTEXT(N'ActorId'));
    -- datetime2(0) округляет дробные секунды: сравниваем с тем же масштабом.
    -- Иначе стандартный DEFAULT на второй половине секунды выглядит как будущее.
    IF EXISTS (SELECT 1 FROM inserted WHERE CreatedAt>CONVERT(datetime2(0),SYSUTCDATETIME())
        OR PlannedStart<CreatedAt OR PlannedEnd<=PlannedStart
        OR (ActualStart IS NOT NULL AND ActualStart<CreatedAt)
        OR (ActualEnd IS NOT NULL AND (ActualStart IS NULL OR ActualEnd<=ActualStart)))
        THROW 51020, N'Некорректная последовательность дат заявки.', 1;
    IF EXISTS (SELECT 1 FROM inserted i LEFT JOIN deleted d ON d.Id=i.Id
        WHERE (d.Id IS NULL AND i.Status NOT IN (N'создана',N'назначена'))
        OR (d.Id IS NOT NULL AND i.Status<>d.Status AND NOT
            ((d.Status=N'создана' AND i.Status IN (N'назначена',N'отменена'))
            OR (d.Status=N'назначена' AND i.Status IN (N'в работе',N'создана',N'отменена'))
            OR (d.Status=N'в работе' AND i.Status IN (N'ожидает материалов',N'выполнена'))
            OR (d.Status=N'ожидает материалов' AND i.Status=N'в работе')
            OR (d.Status=N'выполнена' AND i.Status=N'закрыта'))))
        THROW 51021, N'Недопустимый переход статуса заявки.', 1;
    IF EXISTS (SELECT 1 FROM inserted i JOIN dbo.Equipment e ON e.Id=i.EquipmentId
        WHERE i.Status NOT IN (N'закрыта',N'отменена')
        AND (e.IsDeleted=1 OR e.Status=N'выведено из эксплуатации'))
        THROW 51023, N'Нельзя вести заявку по удалённому или списанному оборудованию.', 1;
    IF EXISTS (SELECT 1 FROM inserted i JOIN dbo.MaintenanceSchedule s ON s.Id=i.ScheduleId
        WHERE i.Type<>N'плановая' OR i.EquipmentId<>s.EquipmentId
            OR i.MaintenanceTypeId IS NULL OR i.MaintenanceTypeId<>s.MaintenanceTypeId)
        THROW 51024, N'Заявка должна соответствовать оборудованию и виду ТО графика.', 1;
    -- UPDLOCK/HOLDLOCK сериализуют проверку по бригаде и закрывают гонку назначений.
    DECLARE @LockedTeams int;
    SELECT @LockedTeams=COUNT(*) FROM dbo.Teams t WITH (UPDLOCK,HOLDLOCK)
        WHERE t.Id IN (SELECT TeamId FROM inserted WHERE TeamId IS NOT NULL);
    IF EXISTS (SELECT 1 FROM inserted i JOIN dbo.WorkOrders w WITH (UPDLOCK,HOLDLOCK)
        ON w.TeamId=i.TeamId AND w.Id<>i.Id
        AND w.PlannedStart<i.PlannedEnd AND i.PlannedStart<w.PlannedEnd
        WHERE i.TeamId IS NOT NULL
        AND i.Status NOT IN (N'выполнена',N'закрыта',N'отменена')
        AND w.Status NOT IN (N'выполнена',N'закрыта',N'отменена'))
        THROW 51022, N'У бригады уже есть заявка с пересекающимся периодом.', 1;
    INSERT dbo.WorkOrderStatusHistory(WorkOrderId,WorkOrderNumber,OldStatus,NewStatus,ChangedBy)
    SELECT i.Id,i.Number,d.Status,i.Status,@Actor
        FROM inserted i LEFT JOIN deleted d ON d.Id=i.Id
        WHERE d.Id IS NULL OR i.Status<>d.Status;
    UPDATE s SET Status=CASE i.Status
        WHEN N'создана' THEN N'запланировано' WHEN N'назначена' THEN N'назначено'
        WHEN N'в работе' THEN N'выполняется' WHEN N'ожидает материалов' THEN N'выполняется'
        WHEN N'выполнена' THEN N'выполнено' WHEN N'закрыта' THEN N'выполнено'
        ELSE N'отменено' END, TeamId=i.TeamId
    FROM dbo.MaintenanceSchedule s JOIN inserted i ON i.ScheduleId=s.Id;
END;
GO
CREATE OR ALTER TRIGGER dbo.TR_WorkOrderMaterials_Stock
ON dbo.WorkOrderMaterials AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;
    IF TRIGGER_NESTLEVEL(OBJECT_ID(N'dbo.TR_WorkOrderMaterials_Stock'))>1 RETURN;
    DECLARE @Actor int=TRY_CONVERT(int,SESSION_CONTEXT(N'ActorId'));
    IF @Actor IS NOT NULL AND EXISTS (SELECT 1 FROM dbo.Users u JOIN dbo.Roles r ON r.Id=u.RoleId
        WHERE u.Id=@Actor AND (u.IsActive=0 OR r.Code NOT IN ('admin','master','member')))
        THROW 51032, N'Роль пользователя не разрешает списание материалов.', 1;
    IF EXISTS (SELECT 1 FROM inserted i JOIN deleted d
        ON d.WorkOrderId=i.WorkOrderId AND d.MaterialId=i.MaterialId
        WHERE i.UnitPrice<>d.UnitPrice)
        THROW 51031, N'Историческая цена списания не изменяется.', 1;
    DECLARE @Delta TABLE(MaterialId int PRIMARY KEY,Quantity decimal(18,3));
    INSERT @Delta SELECT MaterialId,SUM(Quantity) FROM
        (SELECT MaterialId,Quantity FROM inserted
        UNION ALL SELECT MaterialId,-Quantity FROM deleted) q GROUP BY MaterialId;
    -- Одна атомарная операция; отрицательный остаток не возникает даже при конкуренции.
    UPDATE m WITH (UPDLOCK) SET Stock=m.Stock-d.Quantity
        FROM dbo.Materials m JOIN @Delta d ON d.MaterialId=m.Id
        WHERE m.Stock-d.Quantity>=0;
    IF @@ROWCOUNT<>(SELECT COUNT(*) FROM @Delta)
        THROW 51030, N'Недостаточно материала на складе.', 1;
    UPDATE x SET UnitPrice=m.UnitPrice FROM dbo.WorkOrderMaterials x
        JOIN inserted i ON i.WorkOrderId=x.WorkOrderId AND i.MaterialId=x.MaterialId
        JOIN dbo.Materials m ON m.Id=x.MaterialId
        LEFT JOIN deleted d ON d.WorkOrderId=i.WorkOrderId AND d.MaterialId=i.MaterialId
        WHERE d.WorkOrderId IS NULL;
    INSERT dbo.AuditLog(ActorId,Entity,EntityId,Action,OldData,NewData)
    SELECT @Actor,N'WorkOrderMaterials',
        CONCAT(COALESCE(i.WorkOrderId,d.WorkOrderId),N'/',COALESCE(i.MaterialId,d.MaterialId)),
        CASE WHEN d.WorkOrderId IS NULL THEN N'CREATE' WHEN i.WorkOrderId IS NULL THEN N'DELETE' ELSE N'UPDATE' END,
        CASE WHEN d.WorkOrderId IS NOT NULL THEN (SELECT d.* FOR JSON PATH,WITHOUT_ARRAY_WRAPPER) END,
        CASE WHEN i.WorkOrderId IS NOT NULL THEN
            (SELECT x.* FROM dbo.WorkOrderMaterials x WHERE x.WorkOrderId=i.WorkOrderId
             AND x.MaterialId=i.MaterialId FOR JSON PATH,WITHOUT_ARRAY_WRAPPER) END
    FROM inserted i FULL JOIN deleted d ON d.WorkOrderId=i.WorkOrderId AND d.MaterialId=i.MaterialId;
END;
GO
-- Один шаблон создаёт set-based аудит ключевых таблиц с Id.
-- Users: строгий белый список, PasswordHash никогда не попадает в журнал.
DECLARE @Table sysname,@Old nvarchar(max),@New nvarchar(max),@SQL nvarchar(max);
DECLARE AuditTables CURSOR LOCAL FAST_FORWARD FOR SELECT name FROM sys.tables
WHERE schema_id=SCHEMA_ID(N'dbo') AND name IN
    (N'Workshops',N'Roles',N'Teams',N'Users',N'EquipmentTypes',N'MaintenanceTypes',
     N'MaintenanceSchedule',N'WorkOrders',N'Suppliers',N'Materials');
OPEN AuditTables;
FETCH NEXT FROM AuditTables INTO @Table;
WHILE @@FETCH_STATUS=0
BEGIN
    SET @Old=CASE WHEN @Table=N'Users' THEN
        N'd.Id,d.Email,d.Phone,d.LastName,d.FirstName,d.Patronymic,d.RoleId,d.WorkshopId,d.TeamId,d.IsActive'
        ELSE N'd.*' END;
    SET @New=REPLACE(@Old,N'd.',N'i.');
    SET @SQL=N'CREATE OR ALTER TRIGGER dbo.'+QUOTENAME(N'TR_'+@Table+N'_Audit')+
        N' ON dbo.'+QUOTENAME(@Table)+N' AFTER INSERT,UPDATE,DELETE AS BEGIN SET NOCOUNT ON;
        INSERT dbo.AuditLog(ActorId,Entity,EntityId,Action,OldData,NewData)
        SELECT TRY_CONVERT(int,SESSION_CONTEXT(N''ActorId'')),N'''+@Table+N''',
        CONVERT(nvarchar(80),COALESCE(i.Id,d.Id)),
        CASE WHEN d.Id IS NULL THEN N''CREATE'' WHEN i.Id IS NULL THEN N''DELETE'' ELSE N''UPDATE'' END,
        CASE WHEN d.Id IS NOT NULL THEN (SELECT '+@Old+N' FOR JSON PATH,WITHOUT_ARRAY_WRAPPER) END,
        CASE WHEN i.Id IS NOT NULL THEN (SELECT '+@New+N' FOR JSON PATH,WITHOUT_ARRAY_WRAPPER) END
        FROM inserted i FULL JOIN deleted d ON d.Id=i.Id; END;';
    EXEC sys.sp_executesql @SQL;
    FETCH NEXT FROM AuditTables INTO @Table;
END;
CLOSE AuditTables;
DEALLOCATE AuditTables;
GO
CREATE OR ALTER TRIGGER dbo.TR_MaintenanceNorms_Audit ON dbo.MaintenanceNorms AFTER INSERT,UPDATE,DELETE
AS
BEGIN
    SET NOCOUNT ON;
    INSERT dbo.AuditLog(ActorId,Entity,EntityId,Action,OldData,NewData)
    SELECT TRY_CONVERT(int,SESSION_CONTEXT(N'ActorId')),N'MaintenanceNorms',
        CONCAT(COALESCE(i.EquipmentTypeId,d.EquipmentTypeId),N'/',COALESCE(i.MaintenanceTypeId,d.MaintenanceTypeId)),
        CASE WHEN d.EquipmentTypeId IS NULL THEN N'CREATE' WHEN i.EquipmentTypeId IS NULL THEN N'DELETE' ELSE N'UPDATE' END,
        CASE WHEN d.EquipmentTypeId IS NOT NULL THEN (SELECT d.* FOR JSON PATH,WITHOUT_ARRAY_WRAPPER) END,
        CASE WHEN i.EquipmentTypeId IS NOT NULL THEN (SELECT i.* FOR JSON PATH,WITHOUT_ARRAY_WRAPPER) END
    FROM inserted i FULL JOIN deleted d ON d.EquipmentTypeId=i.EquipmentTypeId AND d.MaintenanceTypeId=i.MaintenanceTypeId;
END;
GO
CREATE OR ALTER FUNCTION dbo.CalculateDowntimeHours
(@EquipmentId int,@StartAt datetime2(0),@EndAt datetime2(0)) RETURNS decimal(18,3)
AS
BEGIN
    IF @StartAt IS NULL OR @EndAt IS NULL OR @EndAt<=@StartAt RETURN NULL;
    DECLARE @Hours decimal(18,3),@OpenEnd datetime2(0);
    SET @OpenEnd=CASE WHEN @EndAt>SYSUTCDATETIME() THEN SYSUTCDATETIME() ELSE @EndAt END;
    SELECT @Hours=COALESCE(SUM(CONVERT(decimal(18,3),DATEDIFF_BIG(second,
        CASE WHEN ActualStart<@StartAt THEN @StartAt ELSE ActualStart END,
        CASE WHEN COALESCE(ActualEnd,@OpenEnd)>@EndAt THEN @EndAt ELSE COALESCE(ActualEnd,@OpenEnd) END))/3600.0),0)
    FROM dbo.WorkOrders WHERE EquipmentId=@EquipmentId
        AND Status IN (N'в работе',N'ожидает материалов',N'выполнена',N'закрыта')
        AND ActualStart IS NOT NULL AND ActualStart<@EndAt AND COALESCE(ActualEnd,@OpenEnd)>@StartAt
        AND COALESCE(ActualEnd,@OpenEnd)>ActualStart;
    RETURN @Hours;
END;
GO
CREATE OR ALTER FUNCTION dbo.GetNextMaintenanceDate
(@EquipmentId int,@MaintenanceTypeId int) RETURNS date
AS
BEGIN
    DECLARE @Base date,@Days int;
    SELECT @Days=IntervalDays FROM dbo.MaintenanceTypes WHERE Id=@MaintenanceTypeId AND IntervalKind='days';
    IF @Days IS NULL RETURN NULL; -- По наработке и состоянию календарную дату нельзя вывести без прогноза.
    SELECT @Base=CONVERT(date,MAX(ActualEnd)) FROM dbo.WorkOrders
        WHERE EquipmentId=@EquipmentId AND MaintenanceTypeId=@MaintenanceTypeId
        AND Status IN (N'выполнена',N'закрыта');
    IF @Base IS NULL SELECT @Base=CommissionedOn FROM dbo.Equipment WHERE Id=@EquipmentId;
    RETURN DATEADD(day,@Days,@Base);
END;
GO
CREATE OR ALTER PROCEDURE dbo.GenerateWorkshopReport
    @WorkshopId int,@StartAt datetime2(0),@EndAt datetime2(0)
AS
BEGIN
    SET NOCOUNT ON;
    IF @StartAt IS NULL OR @EndAt IS NULL OR @EndAt<=@StartAt
        THROW 51050, N'Конец отчётного периода должен быть позже начала.', 1;
    IF NOT EXISTS (SELECT 1 FROM dbo.Workshops WHERE Id=@WorkshopId)
        THROW 51051, N'Цех не найден.', 1;
    -- Один результат, одна строка; вложенные списки JSON удобны для API/PDF/Excel.
    SELECT @WorkshopId AS WorkshopId,@StartAt AS StartAt,@EndAt AS EndAt,
        (SELECT COUNT(*) FROM dbo.Equipment WHERE WorkshopId=@WorkshopId AND IsDeleted=0) AS EquipmentCount,
        (SELECT Status,COUNT(*) AS Quantity FROM dbo.Equipment WHERE WorkshopId=@WorkshopId AND IsDeleted=0
            GROUP BY Status FOR JSON PATH) AS EquipmentByStatus,
        (SELECT COUNT(*) FROM dbo.WorkOrders w JOIN dbo.Equipment e ON e.Id=w.EquipmentId
            WHERE e.WorkshopId=@WorkshopId AND w.CreatedAt>=@StartAt AND w.CreatedAt<@EndAt) AS CreatedOrders,
        (SELECT COUNT(*) FROM dbo.WorkOrders w JOIN dbo.Equipment e ON e.Id=w.EquipmentId
            WHERE e.WorkshopId=@WorkshopId AND w.Status IN (N'выполнена',N'закрыта')
            AND w.ActualEnd>=@StartAt AND w.ActualEnd<@EndAt) AS CompletedOrders,
        (SELECT COUNT(*) FROM dbo.WorkOrders w JOIN dbo.Equipment e ON e.Id=w.EquipmentId
            WHERE e.WorkshopId=@WorkshopId AND w.CreatedAt<@EndAt
            AND w.PlannedEnd<@EndAt AND (w.ActualEnd IS NULL OR w.ActualEnd>w.PlannedEnd)
            AND w.Status<>N'отменена') AS OverdueOrders,
        (SELECT COALESCE(SUM(dbo.CalculateDowntimeHours(Id,@StartAt,@EndAt)),0)
            FROM dbo.Equipment WHERE WorkshopId=@WorkshopId) AS DowntimeHours,
        (SELECT COALESCE(AVG(CONVERT(decimal(18,3),DATEDIFF_BIG(second,w.ActualStart,w.ActualEnd))/3600.0),0)
            FROM dbo.WorkOrders w JOIN dbo.Equipment e ON e.Id=w.EquipmentId
            WHERE e.WorkshopId=@WorkshopId AND w.Status IN (N'выполнена',N'закрыта')
            AND w.ActualEnd>=@StartAt AND w.ActualEnd<@EndAt) AS AverageCompletionHours,
        (SELECT TOP (5) w.FailureReason,COUNT(*) AS Quantity FROM dbo.WorkOrders w
            JOIN dbo.Equipment e ON e.Id=w.EquipmentId WHERE e.WorkshopId=@WorkshopId
            AND w.CreatedAt>=@StartAt AND w.CreatedAt<@EndAt AND w.FailureReason IS NOT NULL
            GROUP BY w.FailureReason ORDER BY COUNT(*) DESC,w.FailureReason FOR JSON PATH) AS FrequentFailureReasons,
        (SELECT TOP (5) m.Code,m.Name,m.Unit,SUM(x.Quantity) AS Quantity,
            SUM(x.Quantity*x.UnitPrice) AS Cost FROM dbo.WorkOrderMaterials x
            JOIN dbo.Materials m ON m.Id=x.MaterialId JOIN dbo.WorkOrders w ON w.Id=x.WorkOrderId
            JOIN dbo.Equipment e ON e.Id=w.EquipmentId WHERE e.WorkshopId=@WorkshopId
            AND x.RecordedAt>=@StartAt AND x.RecordedAt<@EndAt
            GROUP BY m.Code,m.Name,m.Unit ORDER BY SUM(x.Quantity) DESC,m.Code FOR JSON PATH) AS TopMaterials;
END;
GO
PRINT N'Правила, аудит, функции и отчёт установлены. Далее 03_seed.sql.';
