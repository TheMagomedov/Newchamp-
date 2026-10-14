-- Интеграционные тесты SQL Server. Запустить после 01/02/03 в ОДНОМ окне SSMS.
-- Каждый случай создаёт свои фикстуры, затем откатывает всю транзакцию.
-- Бизнес-данные не сохраняются; IDENTITY/SEQUENCE могут получить пропуски.
-- Ошибка создания фикстуры всегда FAIL и не считается ожидаемой ошибкой теста.
-- Temp-таблицы и #процедура существуют только в текущем соединении.
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET NUMERIC_ROUNDABORT OFF;
SET NOCOUNT ON;
SET XACT_ABORT ON;
CREATE TABLE #TestResults(TestName nvarchar(150),Passed bit,Details nvarchar(2000));
GO
CREATE PROCEDURE #RunCase @Name nvarchar(150),@Sql nvarchar(max),@ExpectedErrors varchar(100)=''
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    DECLARE @FixtureReady bit=0,@UserId int,@TeamId int,@EquipmentId int,@OrderId int,
        @MaterialId int,@Material2Id int,@TypeId int,@WorkshopId int,@Base datetime2(0);
    BEGIN TRY
        BEGIN TRANSACTION;
        EXEC sys.sp_set_session_context @key=N'ActorId',@value=NULL;
        SELECT @WorkshopId=MIN(Id) FROM dbo.Workshops;
        IF @WorkshopId IS NULL THROW 51989,N'Для тестов сначала загрузите 03_seed.sql.',1;
        INSERT dbo.Users(Email,Phone,LastName,FirstName,PasswordHash,RoleId)
        SELECT CONCAT(N'selftest-',NEWID(),N'@example.invalid'),LEFT(CONVERT(nvarchar(36),NEWID()),30),
            N'SQL',N'Selftest',REPLICATE(N'X',40),Id FROM dbo.Roles WHERE Code='admin';
        SET @UserId=CONVERT(int,SCOPE_IDENTITY());
        EXEC sys.sp_set_session_context @key=N'ActorId',@value=@UserId;
        INSERT dbo.Teams(Code,Name,Specialization,WorkshopId)
            VALUES(N'__SELFTEST__',N'__SQL selftest team__',N'test',@WorkshopId);
        SET @TeamId=CONVERT(int,SCOPE_IDENTITY());
        INSERT dbo.Equipment(InventoryNumber,Name,Model,WorkshopId,CommissionedOn,StartedOn)
            VALUES(N'__SELFTEST__',N'Test equipment',N'Test',@WorkshopId,'20200101','20200102');
        SET @EquipmentId=CONVERT(int,SCOPE_IDENTITY());
        INSERT dbo.MaintenanceTypes(Code,Name,Description,IntervalDays,PlannedHours)
            VALUES(N'__SELFTEST__',N'Test TO',N'Test description',30,4);
        SET @TypeId=CONVERT(int,SCOPE_IDENTITY());
        SET @Base=DATEADD(day,-3,CONVERT(date,SYSUTCDATETIME()));
        INSERT dbo.WorkOrders(EquipmentId,MaintenanceTypeId,MasterId,TeamId,Type,Description,CreatedAt,PlannedStart,PlannedEnd)
            VALUES(@EquipmentId,@TypeId,@UserId,@TeamId,N'плановая',N'Test order',
                @Base,DATEADD(hour,24,@Base),DATEADD(hour,32,@Base));
        SET @OrderId=CONVERT(int,SCOPE_IDENTITY());
        INSERT dbo.Materials(Code,Name,Unit,Stock,MinimumStock,UnitPrice)
            VALUES(N'__TEST_M1__',N'Test material 1',N'кг',10,2,2.50);
        SET @MaterialId=CONVERT(int,SCOPE_IDENTITY());
        INSERT dbo.Materials(Code,Name,Unit,Stock,MinimumStock,UnitPrice)
            VALUES(N'__TEST_M2__',N'Test material 2',N'л',20,3,5.00);
        SET @Material2Id=CONVERT(int,SCOPE_IDENTITY());
        SET @FixtureReady=1;
        EXEC sys.sp_executesql @Sql,
            N'@UserId int,@TeamId int,@EquipmentId int,@OrderId int,@MaterialId int,@Material2Id int,@TypeId int,@WorkshopId int,@Base datetime2(0)',
            @UserId,@TeamId,@EquipmentId,@OrderId,@MaterialId,@Material2Id,@TypeId,@WorkshopId,@Base;
        ROLLBACK TRANSACTION;
        INSERT #TestResults VALUES(@Name,CASE WHEN @ExpectedErrors='' THEN 1 ELSE 0 END,
            CASE WHEN @ExpectedErrors='' THEN N'OK' ELSE N'Ожидаемая ошибка не возникла: '+@ExpectedErrors END);
    END TRY
    BEGIN CATCH
        DECLARE @Error int=ERROR_NUMBER(),@Message nvarchar(2000)=ERROR_MESSAGE();
        IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
        INSERT #TestResults VALUES(@Name,
            CASE WHEN @FixtureReady=1 AND CHARINDEX(','+CONVERT(varchar(12),@Error)+',',','+@ExpectedErrors+',')>0 THEN 1 ELSE 0 END,
            CONCAT(CASE WHEN @FixtureReady=0 THEN N'FIXTURE FAILED: ' ELSE N'' END,@Error,N': ',@Message));
    END CATCH;
    EXEC sys.sp_set_session_context @key=N'ActorId',@value=NULL;
END;
GO
EXEC #RunCase N'01 Уникальный инвентарный номер',N'
INSERT dbo.Equipment(InventoryNumber,Name,Model,WorkshopId,CommissionedOn,StartedOn)
VALUES(N''__SELFTEST__'',N''Duplicate'',N''x'',@WorkshopId,''20200101'',''20200102'');','2601,2627';
EXEC #RunCase N'02 Уникальный email',N'
INSERT dbo.Users(Email,Phone,LastName,FirstName,PasswordHash,RoleId)
SELECT Email,N''unique-selftest-phone'',LastName,FirstName,PasswordHash,RoleId FROM dbo.Users WHERE Id=@UserId;','2601,2627';
EXEC #RunCase N'03 Уникальный телефон',N'
INSERT dbo.Users(Email,Phone,LastName,FirstName,PasswordHash,RoleId)
SELECT N''second-selftest@example.invalid'',Phone,LastName,FirstName,PasswordHash,RoleId FROM dbo.Users WHERE Id=@UserId;','2601,2627';
EXEC #RunCase N'04 Статус оборудования из перечня',N'
UPDATE dbo.Equipment SET Status=N''несуществующий'' WHERE Id=@EquipmentId;','547';
EXEC #RunCase N'05 Дата ввода не в будущем',N'
UPDATE dbo.Equipment SET StartedOn=DATEADD(day,1,CONVERT(date,SYSUTCDATETIME())) WHERE Id=@EquipmentId;','51011';
EXEC #RunCase N'06 Порядок дат оборудования',N'
UPDATE dbo.Equipment SET StartedOn=''20190101'' WHERE Id=@EquipmentId;','547';
EXEC #RunCase N'07 Нельзя вернуть списанное оборудование',N'
UPDATE dbo.Equipment SET Status=N''выведено из эксплуатации'',RetiredOn=''20210101'' WHERE Id=@EquipmentId;
UPDATE dbo.Equipment SET Status=N''в работе'',RetiredOn=NULL WHERE Id=@EquipmentId;','51010';
EXEC #RunCase N'08 FK запрещает удаление оборудования с заявкой',N'
DELETE dbo.Equipment WHERE Id=@EquipmentId;','547';
EXEC #RunCase N'09 Мягкое удаление оборудования с активной заявкой запрещено',N'
UPDATE dbo.Equipment SET IsDeleted=1 WHERE Id=@EquipmentId;','51012';
EXEC #RunCase N'10 Дата создания заявки не в будущем',N'
INSERT dbo.WorkOrders(EquipmentId,MasterId,Type,Description,CreatedAt,PlannedStart,PlannedEnd)
VALUES(@EquipmentId,@UserId,N''текущая'',N''future'',DATEADD(day,1,SYSUTCDATETIME()),
DATEADD(day,2,SYSUTCDATETIME()),DATEADD(day,3,SYSUTCDATETIME()));','51020';
EXEC #RunCase N'11 Плановое начало раньше создания запрещено',N'
UPDATE dbo.WorkOrders SET PlannedStart=DATEADD(day,-1,@Base) WHERE Id=@OrderId;','547';
EXEC #RunCase N'12 Окончание без фактического начала запрещено',N'
UPDATE dbo.WorkOrders SET ActualEnd=@Base WHERE Id=@OrderId;','547';
EXEC #RunCase N'13 Неизвестный приоритет запрещён',N'
UPDATE dbo.WorkOrders SET Priority=N''неизвестен'' WHERE Id=@OrderId;','547';
EXEC #RunCase N'14 Аварийная заявка требует причину',N'
UPDATE dbo.WorkOrders SET Type=N''аварийная'',FailureReason=NULL WHERE Id=@OrderId;','547';
EXEC #RunCase N'15 Нельзя пропустить стадии жизненного цикла',N'
UPDATE dbo.WorkOrders SET Status=N''закрыта'',ActualStart=DATEADD(hour,24,@Base),
ActualEnd=DATEADD(hour,28,@Base),CompletionReport=N''done'' WHERE Id=@OrderId;','51021';
EXEC #RunCase N'16 Полный жизненный цикл и история',N'
UPDATE dbo.WorkOrders SET Status=N''назначена'' WHERE Id=@OrderId;
UPDATE dbo.WorkOrders SET Status=N''в работе'',ActualStart=DATEADD(hour,24,@Base) WHERE Id=@OrderId;
UPDATE dbo.WorkOrders SET Status=N''ожидает материалов'' WHERE Id=@OrderId;
UPDATE dbo.WorkOrders SET Status=N''в работе'' WHERE Id=@OrderId;
UPDATE dbo.WorkOrders SET Status=N''выполнена'',ActualEnd=DATEADD(hour,28,@Base),CompletionReport=N''done'' WHERE Id=@OrderId;
UPDATE dbo.WorkOrders SET Status=N''закрыта'' WHERE Id=@OrderId;
IF (SELECT COUNT(*) FROM dbo.WorkOrderStatusHistory WHERE WorkOrderId=@OrderId)<>7 THROW 51990,N''History count mismatch'',1;';
EXEC #RunCase N'17 Отмена после начала запрещена',N'
UPDATE dbo.WorkOrders SET Status=N''назначена'' WHERE Id=@OrderId;
UPDATE dbo.WorkOrders SET Status=N''в работе'',ActualStart=DATEADD(hour,24,@Base) WHERE Id=@OrderId;
UPDATE dbo.WorkOrders SET Status=N''отменена'' WHERE Id=@OrderId;','547';
EXEC #RunCase N'18 Пересечение назначений бригады запрещено',N'
INSERT dbo.WorkOrders(EquipmentId,MasterId,TeamId,Type,Description,CreatedAt,PlannedStart,PlannedEnd)
VALUES(@EquipmentId,@UserId,@TeamId,N''текущая'',N''overlap'',@Base,DATEADD(hour,25,@Base),DATEADD(hour,26,@Base));','51022';
EXEC #RunCase N'19 Соседние интервалы бригады разрешены',N'
INSERT dbo.WorkOrders(EquipmentId,MasterId,TeamId,Type,Description,CreatedAt,PlannedStart,PlannedEnd)
VALUES(@EquipmentId,@UserId,@TeamId,N''текущая'',N''adjacent'',@Base,DATEADD(hour,32,@Base),DATEADD(hour,33,@Base));';
EXEC #RunCase N'20 Массовое списание, дробное количество и снимок цены',N'
INSERT dbo.WorkOrderMaterials(WorkOrderId,MaterialId,Quantity) VALUES(@OrderId,@MaterialId,1.250),(@OrderId,@Material2Id,2.500);
IF (SELECT Stock FROM dbo.Materials WHERE Id=@MaterialId)<>8.750 OR (SELECT Stock FROM dbo.Materials WHERE Id=@Material2Id)<>17.500
THROW 51990,N''Wrong stock after insert'',1;
IF (SELECT UnitPrice FROM dbo.WorkOrderMaterials WHERE WorkOrderId=@OrderId AND MaterialId=@MaterialId)<>2.50
THROW 51990,N''Historical price not captured'',1;';
EXEC #RunCase N'21 Массовое изменение списаний и возврат',N'
INSERT dbo.WorkOrderMaterials(WorkOrderId,MaterialId,Quantity) VALUES(@OrderId,@MaterialId,1),(@OrderId,@Material2Id,2);
UPDATE dbo.WorkOrderMaterials SET Quantity=Quantity+1 WHERE WorkOrderId=@OrderId;
IF (SELECT Stock FROM dbo.Materials WHERE Id=@MaterialId)<>8 OR (SELECT Stock FROM dbo.Materials WHERE Id=@Material2Id)<>17
THROW 51990,N''Wrong stock after update'',1;
DELETE dbo.WorkOrderMaterials WHERE WorkOrderId=@OrderId;
IF (SELECT Stock FROM dbo.Materials WHERE Id=@MaterialId)<>10 OR (SELECT Stock FROM dbo.Materials WHERE Id=@Material2Id)<>20
THROW 51990,N''Stock not restored'',1;';
EXEC #RunCase N'22 Нехватка одного материала откатывает весь INSERT',N'
INSERT dbo.WorkOrderMaterials(WorkOrderId,MaterialId,Quantity) VALUES(@OrderId,@MaterialId,1),(@OrderId,@Material2Id,21);','51030';
EXEC #RunCase N'23 Историческая цена защищена',N'
INSERT dbo.WorkOrderMaterials(WorkOrderId,MaterialId,Quantity) VALUES(@OrderId,@MaterialId,1);
UPDATE dbo.WorkOrderMaterials SET UnitPrice=999 WHERE WorkOrderId=@OrderId;','51031';
EXEC #RunCase N'24 Цена справочника не меняет старое списание',N'
INSERT dbo.WorkOrderMaterials(WorkOrderId,MaterialId,Quantity) VALUES(@OrderId,@MaterialId,1);
UPDATE dbo.Materials SET UnitPrice=999 WHERE Id=@MaterialId;
IF (SELECT UnitPrice FROM dbo.WorkOrderMaterials WHERE WorkOrderId=@OrderId AND MaterialId=@MaterialId)<>2.5
THROW 51990,N''Historical price changed'',1;';
EXEC #RunCase N'25 DELETE CASCADE списаний, возврат и сохранение истории',N'
INSERT dbo.WorkOrderMaterials(WorkOrderId,MaterialId,Quantity) VALUES(@OrderId,@MaterialId,1);
DECLARE @Number nvarchar(30)=(SELECT Number FROM dbo.WorkOrders WHERE Id=@OrderId);
DELETE dbo.WorkOrders WHERE Id=@OrderId;
IF EXISTS(SELECT 1 FROM dbo.WorkOrderMaterials WHERE WorkOrderId=@OrderId) THROW 51990,N''Cascade failed'',1;
IF (SELECT Stock FROM dbo.Materials WHERE Id=@MaterialId)<>10 THROW 51990,N''Cascade did not restore stock'',1;
IF NOT EXISTS(SELECT 1 FROM dbo.WorkOrderStatusHistory WHERE WorkOrderNumber=@Number AND WorkOrderId IS NULL)
THROW 51990,N''History did not survive deletion'',1;';
EXEC #RunCase N'26 Пользователь удаляется мягко',N'
DELETE dbo.Users WHERE Id=@UserId;
IF NOT EXISTS(SELECT 1 FROM dbo.Users WHERE Id=@UserId AND IsActive=0) THROW 51990,N''User not deactivated'',1;';
EXEC #RunCase N'27 Аудит не хранит хеш пароля',N'
IF EXISTS(SELECT 1 FROM dbo.AuditLog WHERE Entity=N''Users'' AND EntityId=CONVERT(nvarchar(80),@UserId)
AND (NewData LIKE N''%PasswordHash%'' OR NewData LIKE N''%XXXXXXXXXX%'')) THROW 51990,N''Secret in audit'',1;
IF NOT EXISTS(SELECT 1 FROM dbo.AuditLog WHERE Entity=N''Equipment'' AND EntityId=CONVERT(nvarchar(80),@EquipmentId)
AND ActorId=@UserId) THROW 51990,N''Actor missing from audit'',1;';
EXEC #RunCase N'28 Простой обрезается границами периода',N'
UPDATE dbo.WorkOrders SET Status=N''назначена'' WHERE Id=@OrderId;
UPDATE dbo.WorkOrders SET Status=N''в работе'',ActualStart=DATEADD(hour,24,@Base) WHERE Id=@OrderId;
UPDATE dbo.WorkOrders SET Status=N''выполнена'',ActualEnd=DATEADD(hour,28,@Base),CompletionReport=N''done'' WHERE Id=@OrderId;
IF dbo.CalculateDowntimeHours(@EquipmentId,DATEADD(hour,25,@Base),DATEADD(hour,27,@Base))<>2
THROW 51990,N''Expected clipped downtime of 2 hours'',1;';
EXEC #RunCase N'29 Простой пустого периода и некорректных границ',N'
IF dbo.CalculateDowntimeHours(@EquipmentId,@Base,DATEADD(hour,1,@Base))<>0 THROW 51990,N''Expected zero'',1;
IF dbo.CalculateDowntimeHours(@EquipmentId,@Base,@Base) IS NOT NULL THROW 51990,N''Invalid interval should be NULL'',1;';
EXEC #RunCase N'30 Следующее ТО от ввода оборудования',N'
IF dbo.GetNextMaintenanceDate(@EquipmentId,@TypeId)<>CONVERT(date,''20200131'') THROW 51990,N''Wrong first maintenance date'',1;';
EXEC #RunCase N'31 Следующее ТО от последней выполненной заявки',N'
UPDATE dbo.WorkOrders SET Status=N''назначена'' WHERE Id=@OrderId;
UPDATE dbo.WorkOrders SET Status=N''в работе'',ActualStart=DATEADD(hour,24,@Base) WHERE Id=@OrderId;
UPDATE dbo.WorkOrders SET Status=N''выполнена'',ActualEnd=DATEADD(hour,28,@Base),CompletionReport=N''done'' WHERE Id=@OrderId;
IF dbo.GetNextMaintenanceDate(@EquipmentId,@TypeId)<>DATEADD(day,30,CONVERT(date,DATEADD(hour,28,@Base)))
THROW 51990,N''Wrong next maintenance date'',1;';
EXEC #RunCase N'32 Мастер обязан иметь цех',N'
UPDATE dbo.Users SET RoleId=(SELECT Id FROM dbo.Roles WHERE Code=''master''),WorkshopId=NULL WHERE Id=@UserId;','51040';
EXEC #RunCase N'33 Нельзя деактивировать используемый вид ТО',N'
INSERT dbo.MaintenanceSchedule(EquipmentId,MaintenanceTypeId,PlannedAt) VALUES(@EquipmentId,@TypeId,SYSUTCDATETIME());
UPDATE dbo.MaintenanceTypes SET IsActive=0 WHERE Id=@TypeId;','51041';
EXEC #RunCase N'34 Массовый INSERT проверяет каждую строку оборудования',N'
INSERT dbo.Equipment(InventoryNumber,Name,Model,WorkshopId,CommissionedOn,StartedOn) VALUES
(N''__MULTI1__'',N''ok'',N''x'',@WorkshopId,''20200101'',''20200102''),
(N''__MULTI2__'',N''bad'',N''x'',@WorkshopId,''20200101'',DATEADD(day,1,SYSUTCDATETIME()));','51011';
EXEC #RunCase N'35 Отчёт отклоняет обратный период',N'
EXEC dbo.GenerateWorkshopReport @WorkshopId,@Base,@Base;','51050';
EXEC #RunCase N'36 Нулевое количество материала запрещено',N'
INSERT dbo.WorkOrderMaterials(WorkOrderId,MaterialId,Quantity) VALUES(@OrderId,@MaterialId,0);','547';
EXEC #RunCase N'38 Открытый простой не продлевается в будущее',N'
UPDATE dbo.WorkOrders SET Status=N''назначена'' WHERE Id=@OrderId;
UPDATE dbo.WorkOrders SET Status=N''в работе'',ActualStart=DATEADD(hour,24,@Base) WHERE Id=@OrderId;
DECLARE @Now datetime2(0)=SYSUTCDATETIME(),@Expected decimal(18,3),@Actual decimal(18,3);
SET @Expected=CONVERT(decimal(18,3),DATEDIFF_BIG(second,DATEADD(hour,24,@Base),@Now))/3600.0;
SET @Actual=dbo.CalculateDowntimeHours(@EquipmentId,@Base,DATEADD(day,365,@Now));
IF ABS(@Actual-@Expected)>0.002 THROW 51990,N''Open downtime contains future hours'',1;';
EXEC #RunCase N'39 DEFAULT CreatedAt корректен при округлении секунд',N'
-- Начинаем во второй половине секунды: datetime2(0) округляется вверх.
DECLARE @Deadline datetime2(7)=DATEADD(second,2,SYSUTCDATETIME()),@N int=0;
WHILE DATEPART(millisecond,SYSUTCDATETIME())<650 AND SYSUTCDATETIME()<@Deadline
    WAITFOR DELAY ''00:00:00.010'';
WHILE @N<20
BEGIN
    INSERT dbo.WorkOrders(EquipmentId,MasterId,Type,Description,PlannedStart,PlannedEnd)
    VALUES(@EquipmentId,@UserId,N''текущая'',N''Default timestamp precision regression'',
        DATEADD(day,1,SYSUTCDATETIME()),DATEADD(day,2,SYSUTCDATETIME()));
    SET @N+=1;
END;';
GO
INSERT #TestResults VALUES(N'37 Все фикстуры откатились',
    CASE WHEN EXISTS(SELECT 1 FROM dbo.Equipment WHERE InventoryNumber=N'__SELFTEST__')
        OR EXISTS(SELECT 1 FROM dbo.Users WHERE Email LIKE N'selftest-%@example.invalid')
        OR EXISTS(SELECT 1 FROM dbo.Materials WHERE Code IN(N'__TEST_M1__',N'__TEST_M2__'))
        THEN 0 ELSE 1 END,N'После тестов не должно быть временных бизнес-записей');
SELECT TestName,CASE Passed WHEN 1 THEN N'PASS' ELSE N'FAIL' END AS Result,Details
FROM #TestResults ORDER BY TestName;
SELECT COUNT(*) AS Total,SUM(CONVERT(int,Passed)) AS Passed,
    SUM(CASE WHEN Passed=0 THEN 1 ELSE 0 END) AS Failed FROM #TestResults;
IF EXISTS(SELECT 1 FROM #TestResults WHERE Passed=0)
    THROW 51999,N'Есть проваленные SQL-тесты. Смотрите строки FAIL выше.',1;
