using Microsoft.VisualStudio.TestTools.UnitTesting;
using Toir.Desktop;

namespace Toir.Desktop.Tests;

[TestClass]
public sealed class PreviewRulesTests
{
    private DateTime now;
    private WorkOrderDraft valid = null!;
    [TestInitialize]
    public void CreateFreshDeterministicFixture()
    {
        now = new DateTime(2027, 2, 1, 9, 0, 0, DateTimeKind.Utc);
        valid = new WorkOrderDraft(1, "Проверка", "плановая", null, now.AddHours(1), now.AddHours(2));
    }
    [TestMethod]
    public void CalculateDowntimeHoursValidZeroAnd7300HoursReturnsExpectedHours()
    {
        // Arrange: independent timestamps supplied explicitly; no clock access.
        var end = now.AddHours(2.5);
        // Act
        var regular = PreviewRules.calculateDowntimeHours(now, end);
        var longInterval = PreviewRules.calculateDowntimeHours(now, now.AddHours(7300));
        var zero = PreviewRules.calculateDowntimeHours(now, now);
        var parsed = PreviewRules.calculateDowntimeHours("2027-02-01T00:00:00Z", "2027-02-02T00:00:00Z");
        // Assert
        Assert.AreEqual(2.5, regular, 0.00001); Assert.AreEqual(7300d, longInterval, 0.00001);
        Assert.AreEqual(0d, zero); Assert.AreEqual(24d, parsed);
    }
    [TestMethod]
    public void CalculateDowntimeHoursNullMalformedAndNegativeIntervalThrowsInformativeError()
    {
        // Arrange
        DateTime? missing = null;
        // Act
        Action nullStart = () => PreviewRules.calculateDowntimeHours(missing, now);
        Action nullEnd = () => PreviewRules.calculateDowntimeHours(now, missing);
        Action malformed = () => PreviewRules.calculateDowntimeHours("not-a-date", "2027-02-02");
        Action reversed = () => PreviewRules.calculateDowntimeHours(now, now.AddMinutes(-1));
        // Assert
        Assert.AreEqual("Обе даты обязательны.", Assert.Throws<ArgumentException>(nullStart).Message);
        Assert.AreEqual("Обе даты обязательны.", Assert.Throws<ArgumentException>(nullEnd).Message);
        Assert.AreEqual("Неверная дата.", Assert.Throws<ArgumentException>(malformed).Message);
        Assert.AreEqual("Окончание раньше начала.", Assert.Throws<ArgumentException>(reversed).Message);
        Assert.Throws<ArgumentException>(() => PreviewRules.calculateDowntimeHours((string?)null, "2027-02-02"));
    }
    [TestMethod]
    public void ValidateWorkOrderMissingFieldsAndEmergencyReasonReturnsExactErrors()
    {
        // Arrange
        var emergency = valid with { Type = "аварийная" };
        // Act
        var validErrors = PreviewRules.validateWorkOrder(valid, now);
        var missingEquipment = PreviewRules.validateWorkOrder(valid with { EquipmentId = null }, now);
        var missingDescription = PreviewRules.validateWorkOrder(valid with { Description = " " }, now);
        var emergencyErrors = PreviewRules.validateWorkOrder(emergency, now);
        var completeEmergency = PreviewRules.validateWorkOrder(emergency with { FailureReason = "Отказ привода" }, now);
        // Assert
        Assert.IsTrue(validErrors.IsValid); Assert.IsEmpty(validErrors.Errors); Assert.IsTrue(completeEmergency.IsValid);
        CollectionAssert.Contains(missingEquipment.ToList(), "Оборудование обязательно.");
        CollectionAssert.Contains(missingDescription.ToList(), "Описание обязательно.");
        CollectionAssert.Contains(emergencyErrors.ToList(), "Причина обязательна для аварийных заявок");
        CollectionAssert.Contains(PreviewRules.validateWorkOrder(null, now).ToList(), "Заявка обязательна.");
        CollectionAssert.Contains(PreviewRules.validateWorkOrder(valid with { Type = "неизвестно" }, now).ToList(), "Неверный тип заявки.");
    }
    [TestMethod]
    public void ValidateWorkOrderMissingPastAndReversedDatesReturnsDateErrors()
    {
        // Arrange
        var missingStart = valid with { PlannedStart = null }; var missingEnd = valid with { PlannedEnd = null };
        // Act
        var startErrors = PreviewRules.validateWorkOrder(missingStart, now); var endErrors = PreviewRules.validateWorkOrder(missingEnd, now);
        var pastErrors = PreviewRules.validateWorkOrder(valid with { PlannedStart = now.AddDays(-1) }, now);
        var reversedErrors = PreviewRules.validateWorkOrder(valid with { PlannedEnd = now }, now);
        var equalErrors = PreviewRules.validateWorkOrder(valid with { PlannedEnd = valid.PlannedStart }, now);
        // Assert
        CollectionAssert.Contains(startErrors.ToList(), "Плановые даты обязательны.");
        CollectionAssert.Contains(endErrors.ToList(), "Плановые даты обязательны.");
        CollectionAssert.Contains(pastErrors.ToList(), "Плановое начало в прошлом.");
        CollectionAssert.Contains(reversedErrors.ToList(), "Окончание должно быть позже начала.");
        CollectionAssert.Contains(equalErrors.ToList(), "Окончание должно быть позже начала.");
    }
    [TestMethod]
    public void CalculateTotalMaterialCostThreeMaterialsZerosAndInvalidValuesReturns7300OrError()
    {
        // Arrange: bearings 5000 + belts 1500 + oil 800 = 7300.
        MaterialPreview[] materials = [new(2, 2500, "Подшипник"), new(3, 500, "Ремень"), new(4, 200, "Масло")];
        MaterialPreview[] withZeros = [.. materials, new(0, 500), new(7, 0)];
        // Act
        var total = PreviewRules.calculateTotalMaterialCost(materials); var mixed = PreviewRules.calculateTotalMaterialCost(withZeros);
        var empty = PreviewRules.calculateTotalMaterialCost([]); var decimals = PreviewRules.calculateTotalMaterialCost([new(3, 0.01m)]);
        // Assert
        Assert.AreEqual(7300m, total); Assert.AreEqual(total, mixed); Assert.AreEqual(0m, empty); Assert.AreEqual(0.03m, decimals);
        Assert.AreEqual(0m, PreviewRules.calculateTotalMaterialCost([new(0, 50), new(5, 0)]));
        Assert.Throws<ArgumentNullException>(() => PreviewRules.calculateTotalMaterialCost(null));
        Assert.AreEqual("Количество и цена не могут быть отрицательными.", Assert.Throws<ArgumentException>(() => PreviewRules.calculateTotalMaterialCost([new(-1, 2)])).Message);
        Assert.AreEqual("Количество и цена не могут быть отрицательными.", Assert.Throws<ArgumentException>(() => PreviewRules.calculateTotalMaterialCost([new(1, -2)])).Message);
    }
}
