using System.Globalization;
using System.Text.Json.Nodes;

namespace Toir.Desktop;

public static class TransitionPayload
{
    // An unchanged value in a stale form must never overwrite a newer server value.
    // Assignment is explicit: the brigade shown in that workflow is the user's choice.
    public static JsonObject Build(JsonObject edited, JsonNode original)
    {
        var status = edited["status"]?.ToString() ?? "";
        var payload = new JsonObject { ["status"] = status };
        if (status == "назначена" && edited["team_id"] is null)
            throw new InvalidOperationException("Выберите бригаду для назначения.");
        foreach (var (input, field) in new[] { ("team_id", "TeamId"), ("actual_start", "ActualStart"), ("actual_end", "ActualEnd"), ("completion_report", "CompletionReport") })
        {
            if (!edited.TryGetPropertyValue(input, out var value)) continue;
            if (input == "team_id" && status == "назначена" || !Equivalent(input, value, original[field]))
                payload[input] = value?.DeepClone();
        }
        return payload;
    }
    private static bool Equivalent(string field, JsonNode? left, JsonNode? right)
    {
        var a = left?.ToString().Trim() ?? ""; var b = right?.ToString().Trim() ?? "";
        if (field is "actual_start" or "actual_end" &&
            DateTimeOffset.TryParse(a, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var x) &&
            DateTimeOffset.TryParse(b, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var y)) return x == y;
        return a == b;
    }
}
