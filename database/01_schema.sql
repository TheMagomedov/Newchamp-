-- ТОиР-Проф: учебная схема. SQL Server 2022+, существующая ПУСТАЯ пользовательская БД.
-- Выбрать БД в SSMS. Выполнять целиком: 01_schema -> 02_rules -> 03_seed.
-- UTC для datetime2; календарные даты оборудования трактуются в UTC.
-- Без CREATE DATABASE, USE и DROP. Повторный запуск намеренно запрещён.
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET NUMERIC_ROUNDABORT OFF;
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF DB_NAME() IN (N'master',N'model',N'msdb',N'tempdb')
    THROW 51000, N'Выберите отдельную пустую учебную БД.', 1;
IF EXISTS (SELECT 1 FROM sys.tables WHERE is_ms_shipped = 0)
    THROW 51001, N'БД содержит таблицы. Схема рассчитана на пустую БД.', 1;
BEGIN TRANSACTION;

CREATE TABLE dbo.Workshops (
    Id int IDENTITY PRIMARY KEY,
    Code nvarchar(20) NOT NULL UNIQUE,
    Name nvarchar(120) NOT NULL UNIQUE
);
CREATE TABLE dbo.Roles (
    Id int IDENTITY PRIMARY KEY,
    Code varchar(20) NOT NULL UNIQUE,
    Name nvarchar(80) NOT NULL UNIQUE
);
CREATE TABLE dbo.Teams (
    Id int IDENTITY PRIMARY KEY,
    Code nvarchar(20) NOT NULL UNIQUE,
    Name nvarchar(100) NOT NULL UNIQUE,
    Specialization nvarchar(100) NOT NULL,
    WorkshopId int NULL REFERENCES dbo.Workshops(Id),
    IsActive bit NOT NULL DEFAULT 1
);
CREATE TABLE dbo.Users (
    Id int IDENTITY PRIMARY KEY,
    Email nvarchar(254) NOT NULL UNIQUE,
    Phone nvarchar(30) NOT NULL UNIQUE,
    LastName nvarchar(60) NOT NULL,
    FirstName nvarchar(60) NOT NULL,
    Patronymic nvarchar(60) NULL,
    PasswordHash nvarchar(512) NOT NULL,
    RoleId int NOT NULL REFERENCES dbo.Roles(Id),
    WorkshopId int NULL REFERENCES dbo.Workshops(Id),
    TeamId int NULL REFERENCES dbo.Teams(Id),
    RegisteredAt datetime2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
    IsActive bit NOT NULL DEFAULT 1,
    CONSTRAINT CK_Users_Email CHECK (Email LIKE N'%_@_%._%'),
    CONSTRAINT CK_Users_Hash CHECK (LEN(PasswordHash) >= 30)
);
CREATE TABLE dbo.EquipmentTypes (
    Id int IDENTITY PRIMARY KEY,
    Code nvarchar(30) NOT NULL UNIQUE,
    Name nvarchar(120) NOT NULL UNIQUE
);
CREATE TABLE dbo.Equipment (
    Id int IDENTITY PRIMARY KEY,
    InventoryNumber nvarchar(40) NOT NULL UNIQUE,
    Name nvarchar(150) NOT NULL,
    Model nvarchar(100) NOT NULL,
    SerialNumber nvarchar(100) NULL,
    WorkshopId int NOT NULL REFERENCES dbo.Workshops(Id),
    EquipmentTypeId int NULL REFERENCES dbo.EquipmentTypes(Id),
    CommissionedOn date NOT NULL,
    StartedOn date NOT NULL,
    RetiredOn date NULL,
    Status nvarchar(30) NOT NULL DEFAULT N'в работе',
    Manufacturer nvarchar(120) NULL,
    WarrantyUntil date NULL,
    PassportUrl nvarchar(1000) NULL,
    IsDeleted bit NOT NULL DEFAULT 0,
    CreatedAt datetime2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
    UpdatedAt datetime2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
    CreatedBy int NULL REFERENCES dbo.Users(Id),
    UpdatedBy int NULL REFERENCES dbo.Users(Id),
    CONSTRAINT CK_Equipment_Status CHECK (Status IN
        (N'в работе',N'в ремонте',N'в простое',N'выведено из эксплуатации')),
    CONSTRAINT CK_Equipment_Dates CHECK (CommissionedOn <= StartedOn
        AND (RetiredOn IS NULL OR RetiredOn > CommissionedOn)),
    CONSTRAINT CK_Equipment_Retired CHECK
        ((Status = N'выведено из эксплуатации' AND RetiredOn IS NOT NULL)
        OR (Status <> N'выведено из эксплуатации' AND RetiredOn IS NULL))
);
CREATE TABLE dbo.MaintenanceTypes (
    Id int IDENTITY PRIMARY KEY,
    Code nvarchar(20) NOT NULL UNIQUE,
    Name nvarchar(100) NOT NULL,
    Description nvarchar(2000) NOT NULL,
    IntervalKind varchar(12) NOT NULL DEFAULT 'days'
        CHECK (IntervalKind IN ('days','hours','condition')),
    IntervalDays int NULL,
    IntervalHours decimal(12,2) NULL,
    PlannedHours decimal(8,2) NOT NULL CHECK (PlannedHours > 0),
    RequiresStop bit NOT NULL DEFAULT 1,
    IsActive bit NOT NULL DEFAULT 1,
    CONSTRAINT CK_MaintenanceTypes_Interval CHECK
        ((IntervalKind = 'days' AND IntervalDays IS NOT NULL AND IntervalDays > 0 AND IntervalHours IS NULL)
        OR (IntervalKind = 'hours' AND IntervalHours IS NOT NULL AND IntervalHours > 0 AND IntervalDays IS NULL)
        OR (IntervalKind = 'condition' AND IntervalDays IS NULL AND IntervalHours IS NULL))
);
CREATE TABLE dbo.MaintenanceNorms (
    EquipmentTypeId int NOT NULL REFERENCES dbo.EquipmentTypes(Id),
    MaintenanceTypeId int NOT NULL REFERENCES dbo.MaintenanceTypes(Id),
    MinimumHours decimal(8,2) NOT NULL CHECK (MinimumHours > 0),
    MaximumHours decimal(8,2) NOT NULL,
    PRIMARY KEY (EquipmentTypeId,MaintenanceTypeId),
    CHECK (MaximumHours >= MinimumHours)
);
CREATE TABLE dbo.MaintenanceSchedule (
    Id int IDENTITY PRIMARY KEY,
    EquipmentId int NOT NULL REFERENCES dbo.Equipment(Id),
    MaintenanceTypeId int NOT NULL REFERENCES dbo.MaintenanceTypes(Id),
    PlannedAt datetime2(0) NOT NULL,
    Status nvarchar(20) NOT NULL DEFAULT N'запланировано',
    TeamId int NULL REFERENCES dbo.Teams(Id),
    CancellationReason nvarchar(1000) NULL,
    CONSTRAINT CK_Schedule_Status CHECK (Status IN
        (N'запланировано',N'назначено',N'выполняется',N'выполнено',N'отменено',N'просрочено')),
    CONSTRAINT UQ_Schedule UNIQUE (EquipmentId,MaintenanceTypeId,PlannedAt)
);
CREATE SEQUENCE dbo.WorkOrderNumber AS bigint START WITH 1 INCREMENT BY 1;
CREATE TABLE dbo.WorkOrders (
    Id int IDENTITY PRIMARY KEY,
    SequenceNumber bigint NOT NULL DEFAULT (NEXT VALUE FOR dbo.WorkOrderNumber),
    CreatedAt datetime2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
    Number AS (N'Z-' + CONVERT(nvarchar(4),DATEPART(year,CreatedAt))
        + N'-' + CONVERT(nvarchar(20),SequenceNumber)) PERSISTED,
    EquipmentId int NOT NULL REFERENCES dbo.Equipment(Id),
    MaintenanceTypeId int NULL REFERENCES dbo.MaintenanceTypes(Id),
    ScheduleId int NULL REFERENCES dbo.MaintenanceSchedule(Id),
    MasterId int NOT NULL REFERENCES dbo.Users(Id),
    TeamId int NULL REFERENCES dbo.Teams(Id),
    Type nvarchar(15) NOT NULL,
    Priority nvarchar(15) NOT NULL DEFAULT N'средний',
    Status nvarchar(20) NOT NULL DEFAULT N'создана',
    Description nvarchar(2000) NOT NULL,
    FailureReason nvarchar(500) NULL,
    PlannedStart datetime2(0) NOT NULL,
    PlannedEnd datetime2(0) NOT NULL,
    ActualStart datetime2(0) NULL,
    ActualEnd datetime2(0) NULL,
    CompletionReport nvarchar(2000) NULL,
    Version rowversion,
    CONSTRAINT UQ_WorkOrders_Number UNIQUE (Number),
    CONSTRAINT CK_WorkOrders_Type CHECK (Type IN (N'плановая',N'аварийная',N'текущая')),
    CONSTRAINT CK_WorkOrders_Priority CHECK (Priority IN (N'низкий',N'средний',N'высокий',N'критический')),
    CONSTRAINT CK_WorkOrders_Status CHECK (Status IN
        (N'создана',N'назначена',N'в работе',N'ожидает материалов',N'выполнена',N'закрыта',N'отменена')),
    CONSTRAINT CK_WorkOrders_Dates CHECK (PlannedStart >= CreatedAt AND PlannedEnd > PlannedStart
        AND (ActualStart IS NULL OR ActualStart >= CreatedAt)
        AND (ActualEnd IS NULL OR (ActualStart IS NOT NULL AND ActualEnd > ActualStart))),
    CONSTRAINT CK_WorkOrders_Reason CHECK (Type <> N'аварийная'
        OR (FailureReason IS NOT NULL AND LEN(LTRIM(RTRIM(FailureReason))) > 0)),
    CONSTRAINT CK_WorkOrders_Cancel CHECK (Status <> N'отменена' OR ActualStart IS NULL),
    CONSTRAINT CK_WorkOrders_Done CHECK (Status NOT IN (N'выполнена',N'закрыта')
        OR (ActualEnd IS NOT NULL AND CompletionReport IS NOT NULL AND LEN(CompletionReport) > 0)),
    CONSTRAINT CK_WorkOrders_Started CHECK (Status NOT IN (N'в работе',N'ожидает материалов')
        OR ActualStart IS NOT NULL),
    CONSTRAINT CK_WorkOrders_Team CHECK (Status NOT IN
        (N'назначена',N'в работе',N'ожидает материалов',N'выполнена',N'закрыта') OR TeamId IS NOT NULL)
);
CREATE UNIQUE INDEX UX_WorkOrders_Schedule ON dbo.WorkOrders(ScheduleId) WHERE ScheduleId IS NOT NULL;
CREATE TABLE dbo.Suppliers (
    Id int IDENTITY PRIMARY KEY,
    Name nvarchar(150) NOT NULL UNIQUE,
    Phone nvarchar(30) NULL
);
CREATE TABLE dbo.Materials (
    Id int IDENTITY PRIMARY KEY,
    Code nvarchar(40) NOT NULL UNIQUE,
    Name nvarchar(150) NOT NULL,
    Unit nvarchar(20) NOT NULL,
    Stock decimal(14,3) NOT NULL DEFAULT 0 CHECK (Stock >= 0),
    MinimumStock decimal(14,3) NOT NULL DEFAULT 0 CHECK (MinimumStock >= 0),
    Location nvarchar(80) NULL,
    UnitPrice decimal(14,2) NOT NULL CHECK (UnitPrice >= 0),
    SupplierId int NULL REFERENCES dbo.Suppliers(Id)
);
CREATE TABLE dbo.WorkOrderMaterials (
    WorkOrderId int NOT NULL REFERENCES dbo.WorkOrders(Id) ON DELETE CASCADE,
    MaterialId int NOT NULL REFERENCES dbo.Materials(Id),
    Quantity decimal(14,3) NOT NULL CHECK (Quantity > 0),
    UnitPrice decimal(14,2) NOT NULL DEFAULT 0 CHECK (UnitPrice >= 0),
    RecordedAt datetime2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
    Comment nvarchar(500) NULL,
    PRIMARY KEY (WorkOrderId,MaterialId)
);
-- История заявки сохраняет номер: физическое удаление только ещё не начатой заявки.
CREATE TABLE dbo.WorkOrderStatusHistory (
    Id bigint IDENTITY PRIMARY KEY,
    WorkOrderId int NULL REFERENCES dbo.WorkOrders(Id) ON DELETE SET NULL,
    WorkOrderNumber nvarchar(30) NOT NULL,
    OldStatus nvarchar(20) NULL,
    NewStatus nvarchar(20) NOT NULL,
    ChangedAt datetime2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
    ChangedBy int NULL REFERENCES dbo.Users(Id)
);
CREATE TABLE dbo.EquipmentStatusHistory (
    Id bigint IDENTITY PRIMARY KEY,
    EquipmentId int NULL REFERENCES dbo.Equipment(Id) ON DELETE SET NULL,
    InventoryNumber nvarchar(40) NOT NULL,
    OldStatus nvarchar(30) NULL,
    NewStatus nvarchar(30) NOT NULL,
    ChangedAt datetime2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
    ChangedBy int NULL REFERENCES dbo.Users(Id)
);
CREATE TABLE dbo.AuditLog (
    Id bigint IDENTITY PRIMARY KEY,
    ActorId int NULL REFERENCES dbo.Users(Id),
    Entity nvarchar(50) NOT NULL,
    EntityId nvarchar(80) NOT NULL,
    Action nvarchar(20) NOT NULL,
    OldData nvarchar(max) NULL,
    NewData nvarchar(max) NULL,
    OccurredAt datetime2(0) NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE dbo.RefreshTokens (
    Id bigint IDENTITY PRIMARY KEY,
    UserId int NOT NULL REFERENCES dbo.Users(Id),
    TokenHash binary(32) NOT NULL UNIQUE,
    CreatedAt datetime2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
    ExpiresAt datetime2(0) NOT NULL,
    RevokedAt datetime2(0) NULL,
    CONSTRAINT CK_RefreshTokens_Expiry CHECK (ExpiresAt > CreatedAt)
);
CREATE TABLE dbo.ClientRequests (
    UserId int NOT NULL REFERENCES dbo.Users(Id),
    RequestKey varchar(100) NOT NULL,
    Fingerprint char(64) NOT NULL,
    Response nvarchar(max) NOT NULL,
    CreatedAt datetime2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
    PRIMARY KEY (UserId,RequestKey)
);
CREATE INDEX IX_Users_Role ON dbo.Users(RoleId);
CREATE INDEX IX_Users_Team ON dbo.Users(TeamId);
CREATE INDEX IX_Equipment_WorkshopStatus ON dbo.Equipment(WorkshopId,Status);
CREATE INDEX IX_Schedule_StatusDate ON dbo.MaintenanceSchedule(Status,PlannedAt);
CREATE INDEX IX_WorkOrders_Equipment ON dbo.WorkOrders(EquipmentId,ActualStart) INCLUDE (ActualEnd,Status);
CREATE INDEX IX_WorkOrders_TeamPeriod ON dbo.WorkOrders(TeamId,PlannedStart,PlannedEnd) INCLUDE (Status);
CREATE INDEX IX_WorkOrders_Status ON dbo.WorkOrders(Status,CreatedAt);
CREATE INDEX IX_WorkOrderMaterials_Material ON dbo.WorkOrderMaterials(MaterialId);
CREATE INDEX IX_EquipmentHistory ON dbo.EquipmentStatusHistory(EquipmentId,ChangedAt);
CREATE INDEX IX_OrderHistory ON dbo.WorkOrderStatusHistory(WorkOrderId,ChangedAt);
CREATE INDEX IX_Audit_Entity ON dbo.AuditLog(Entity,EntityId,OccurredAt);
COMMIT TRANSACTION;
PRINT N'Схема создана. Затем выполните 02_rules.sql.';


