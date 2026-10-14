namespace Toir.Desktop;

// Учебный модуль: показатели, диаграммы и краткие списки на главном экране.
public partial class MainWindow
{
    private void RenderDashboard(JsonNode data)
    {
        var body = new StackPanel(); ContentHost.Children.Clear(); ContentHost.Children.Add(new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto });
        var cards = new System.Windows.Controls.Primitives.UniformGrid { Columns = 3 };
        var metrics = data["metrics"];
        foreach (var (key, title) in new[] { ("equipment", "Единиц оборудования"), ("open_orders", "Активных заявок"), ("today_orders", "Заявок на сегодня"), ("avg_completion_hours", "Среднее выполнение, ч"), ("overdue", "Просроченных заявок"), ("low_stock", "Дефицитных материалов") })
        {
            var content = new StackPanel(); content.Children.Add(Ui.Text(title, 12)); content.Children.Add(Ui.Text(metrics.Text(key, "—"), 28, true)); content.Children.Add(Ui.Text(TrendLabel(data, key), 10)); cards.Children.Add(Ui.Card(content));
        }
        body.Children.Add(cards);
        var charts = new Grid(); charts.ColumnDefinitions.Add(new()); charts.ColumnDefinitions.Add(new());
        var left = RenderBars("Состояние оборудования", data["equipment_status"]); var right = RenderBars("Заказы по статусу", data["orders_by_status"]);
        charts.Children.Add(left); Grid.SetColumn(right, 1); charts.Children.Add(right); body.Children.Add(charts);
        foreach (var (key, label) in new[] { ("active_orders", "Активные заявки • дважды нажмите для подробностей"), ("upcoming", "Обслуживание на 7 дней"), ("low_stock", "Пополнить склад") })
        {
            body.Children.Add(Ui.Text(label, 18, true));
            var columns = key switch { "active_orders" => new[] { "Id", "Number", "DisplayNumber", "EquipmentName", "EquipmentId", "Status", "Priority", "CreatedAt" }, "upcoming" => new[] { "EquipmentName", "EquipmentId", "MaintenanceTypeName", "MaintenanceTypeId", "PlannedAt", "Status" }, _ => new[] { "Name", "Unit", "Stock", "MinimumStock" } };
            var rows = data[key].Rows().Select(row => (JsonNode)new JsonObject(columns.Where(c => row[c] is not null && !(c.EndsWith("Id") && row[c[..^2] + "Name"] is not null)).Select(c => new KeyValuePair<string, JsonNode?>(c, row[c]!.DeepClone())))).ToList();
            if (rows.Count == 0) body.Children.Add(Ui.Text("Записей нет", 12));
            else { var table = MakeTable(rows); table.Grid.MaxHeight = 245; table.Grid.Margin = new Thickness(0, 0, 12, 20); if (key == "active_orders") table.Grid.MouseDoubleClick += async (_, _) => { if (table.Selected() is { } r) await ShowOrderDetails(r.Int("Id")); }; body.Children.Add(table.Grid); }
        }
    }
    private Border RenderBars(string title, JsonNode? values)
    {
        var panel = new StackPanel(); panel.Children.Add(Ui.Text(title, 17, true));
        var rows = values.Rows().ToList(); double Value(JsonNode r) => double.TryParse(r.Text("value"), System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out var n) ? n : 0; var max = Math.Max(1, rows.Select(Value).DefaultIfEmpty(1).Max());
        foreach (var row in rows)
        {
            panel.Children.Add(Ui.Text($"{row.Text("label")}  ·  {row.Text("value")}", 12));
            panel.Children.Add(new ProgressBar { Value = Math.Max(0, Value(row)), Maximum = max, Height = 8, Foreground = new SolidColorBrush(Color.FromRgb(8, 127, 130)), Background = new SolidColorBrush(Color.FromRgb(229, 239, 240)), Margin = new Thickness(0, 0, 0, 12) });
        }
        if (rows.Count == 0) panel.Children.Add(Ui.Text("Пока нет данных", 12)); return Ui.Card(panel);
    }
    private static string TrendLabel(JsonNode data, string key)
    {
        var trend = data["trends"]?[key] ?? data["kpi_trends"]?[key];
        if (trend?.Bool("available") != true) return "Тренд: нет сопоставимой истории";
        return "Δ " + trend.Text("delta", "—") + (trend["percent"] is null ? "" : " (" + trend.Text("percent") + "%)") + " к предыдущему периоду";
    }
}
