using System.Globalization;

namespace Toir.Desktop;

// Pure, deterministic presentation/preflight helpers. They never change authoritative data.
// API/SQL validation and calculations remain mandatory even after a successful local preview.
public static class PreviewRules
{
    public static double calculateDowntimeHours(DateTime? start, DateTime? end)
    {
        if (start is null || end is null) throw new ArgumentException("Обе даты обязательны.");
        if (end < start) throw new ArgumentException("Окончание раньше начала.");
        return (end.Value - start.Value).TotalHours;
    }
    public static double calculateDowntimeHours(string? start, string? end)
    {
        if (!DateTime.TryParse(start, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out var a) ||
            !DateTime.TryParse(end, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out var b))
            throw new ArgumentException("Неверная дата.");
        return calculateDowntimeHours(a, b);
    }
    public static WorkOrderValidation validateWorkOrder(WorkOrderDraft? draft, DateTime now)
    {
        if (draft is null) return new(["Заявка обязательна."]);
        var errors = new List<string>();
        if (draft.EquipmentId is null or <= 0) errors.Add("Оборудование обязательно.");
        if (string.IsNullOrWhiteSpace(draft.Description)) errors.Add("Описание обязательно.");
        if (draft.Type is not ("плановая" or "аварийная" or "текущая")) errors.Add("Неверный тип заявки.");
        if (draft.Type == "аварийная" && string.IsNullOrWhiteSpace(draft.FailureReason)) errors.Add("Причина обязательна для аварийных заявок");
        if (draft.PlannedStart is null || draft.PlannedEnd is null) errors.Add("Плановые даты обязательны.");
        else
        {
            if (draft.PlannedEnd <= draft.PlannedStart) errors.Add("Окончание должно быть позже начала.");
            if (draft.PlannedStart < now) errors.Add("Плановое начало в прошлом.");
        }
        return new(errors);
    }
    public static decimal calculateTotalMaterialCost(IEnumerable<MaterialPreview>? materials)
    {
        ArgumentNullException.ThrowIfNull(materials);
        decimal total = 0;
        foreach (var row in materials)
        {
            if (row.Quantity < 0 || row.UnitPrice < 0) throw new ArgumentException("Количество и цена не могут быть отрицательными.");
            total += row.Quantity * row.UnitPrice;
        }
        return decimal.Round(total, 2, MidpointRounding.AwayFromZero);
    }
}
public record WorkOrderDraft(int? EquipmentId, string? Description, string? Type, string? FailureReason, DateTime? PlannedStart, DateTime? PlannedEnd);
public record MaterialPreview(decimal Quantity, decimal UnitPrice, string? Name = null);
public sealed class WorkOrderValidation(IReadOnlyList<string> errors) : IReadOnlyList<string>
{
    public bool IsValid => errors.Count == 0;
    public IReadOnlyList<string> Errors => errors;
    public int Count => errors.Count;
    public string this[int index] => errors[index];
    public IEnumerator<string> GetEnumerator() => errors.GetEnumerator();
    System.Collections.IEnumerator System.Collections.IEnumerable.GetEnumerator() => GetEnumerator();
}
