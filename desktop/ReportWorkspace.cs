namespace Toir.Desktop;

public partial class MainWindow
{
    private static readonly EditorDialog.Choice[] ReportTypes = [new("downtime", "Простои оборудования"), new("schedule", "Выполнение ТО"), new("team-efficiency", "Эффективность бригад"), new("material-usage", "Расход материалов"), new("equipment", "Реестр оборудования"), new("work-orders", "Реестр заявок"), new("materials", "Остатки материалов")];
    private void RenderReportWorkspace()
    {
        ContentHost.Children.Clear(); var root = new DockPanel(); ContentHost.Children.Add(root);
        var top = new StackPanel { Margin = new Thickness(0, 0, 0, 14) }; DockPanel.SetDock(top, Dock.Top); root.Children.Add(top);
        var parameters = new WrapPanel(); top.Children.Add(parameters);
        ComboBox Select(IEnumerable<EditorDialog.Choice> items, double width) => new() { Width = width, Margin = new Thickness(0, 0, 10, 10), DisplayMemberPath = "Label", SelectedValuePath = "Value", ItemsSource = items, SelectedIndex = 0 };
        var kind = Select(ReportTypes, 215); parameters.Children.Add(kind);
        var workshops = new List<EditorDialog.Choice> { new("", "Все доступные цеха") }; workshops.AddRange(lookups["workshops"].Rows().Select(x => new EditorDialog.Choice(x.Text("id"), x.Text("label"))));
        var workshop = Select(workshops, 170); parameters.Children.Add(workshop);
        var from = new DatePicker { SelectedDate = DateTime.Today.AddDays(-30), Width = 145, Margin = new Thickness(0, 0, 10, 10), ToolTip = "Период с (UTC)" }; parameters.Children.Add(from);
        var to = new DatePicker { SelectedDate = DateTime.Today, Width = 145, Margin = new Thickness(0, 0, 10, 10), ToolTip = "Период по (UTC)" }; parameters.Children.Add(to);
        var format = new ComboBox { Width = 80, ItemsSource = new[] { "pdf", "xlsx", "csv" }, SelectedIndex = 0, Margin = new Thickness(0, 0, 10, 10) }; parameters.Children.Add(format);
        var templates = LocalStore.Read(api.UserFile("report-templates")) as JsonObject ?? new JsonObject();
        var templateLine = new WrapPanel(); top.Children.Add(templateLine);
        var template = new ComboBox { Width = 200, ItemsSource = templates.Select(x => x.Key).ToList(), Margin = new Thickness(0, 0, 10, 10) }; templateLine.Children.Add(template);
        var templateName = new TextBox { Width = 180, ToolTip = "Имя нового шаблона", Margin = new Thickness(0, 0, 10, 10) }; templateLine.Children.Add(templateName);
        JsonObject Payload()
        {
            if (from.SelectedDate > to.SelectedDate) throw new InvalidOperationException("Начало периода позже окончания.");
            var payload = new JsonObject { ["type"] = kind.SelectedValue?.ToString(), ["format"] = format.SelectedItem?.ToString() };
            if (from.SelectedDate is { } a) payload["from"] = a.ToString("yyyy-MM-dd");
            if (to.SelectedDate is { } b) payload["to"] = b.ToString("yyyy-MM-dd");
            if (int.TryParse(workshop.SelectedValue?.ToString(), out var id)) payload["workshop_id"] = id;
            return payload;
        }
        templateLine.Children.Add(Ui.Button("Применить шаблон", (_, _) =>
        {
            if (template.SelectedItem is not string name || templates[name] is not JsonObject settings) return;
            kind.SelectedValue = settings.Text("type"); workshop.SelectedValue = settings.Text("workshop_id"); format.SelectedItem = settings.Text("format", "pdf");
            from.SelectedDate = DateTime.TryParse(settings.Text("from"), out var a) ? a : null; to.SelectedDate = DateTime.TryParse(settings.Text("to"), out var b) ? b : null;
        }, true));
        templateLine.Children.Add(Ui.Button("Сохранить шаблон", (_, _) =>
        {
            try
            {
                var name = templateName.Text.Trim(); if (name.Length is < 1 or > 80) throw new InvalidOperationException("Введите название шаблона (1–80 символов).");
                templates[name] = Payload(); LocalStore.Write(api.UserFile("report-templates"), templates); template.ItemsSource = templates.Select(x => x.Key).ToList(); template.SelectedItem = name; Toast("Шаблон сохранён");
            }
            catch (Exception e) { Notify(e.Message); }
        }, true));
        templateLine.Children.Add(Ui.Button("Удалить шаблон", (_, _) =>
        {
            if (template.SelectedItem is string name && MessageBox.Show(this, "Удалить шаблон «" + name + "»?", "Шаблон", MessageBoxButton.YesNo) == MessageBoxResult.Yes) { templates.Remove(name); LocalStore.Write(api.UserFile("report-templates"), templates); template.ItemsSource = templates.Select(x => x.Key).ToList(); }
        }, true));
        var actions = new WrapPanel { Margin = new Thickness(0, 4, 0, 8) }; top.Children.Add(actions);
        var preview = new StackPanel(); root.Children.Add(new ScrollViewer { Content = preview, VerticalScrollBarVisibility = ScrollBarVisibility.Auto });
        var progress = new ProgressBar { Height = 4, IsIndeterminate = true, Visibility = Visibility.Collapsed }; top.Children.Add(progress);
        var message = Ui.Text("Выберите параметры и сформируйте предпросмотр. Данные берутся с сервера.", 12); top.Children.Add(message);
        var show = new Button { Content = "Предпросмотр" }; actions.Children.Add(show);
        var export = new Button { Content = "Экспорт и открыть" }; actions.Children.Add(export);
        async Task Run(Func<Task> action)
        {
            show.IsEnabled = export.IsEnabled = false; progress.Visibility = Visibility.Visible;
            try { await action(); }
            catch (Exception e) { message.Text = e.Message; }
            finally { show.IsEnabled = export.IsEnabled = true; progress.Visibility = Visibility.Collapsed; }
        }
        show.Click += async (_, _) => await Run(async () =>
        {
            var payload = Payload(); var query = string.Join("&", payload.Where(x => x.Key != "format").Select(x => x.Key + "=" + Uri.EscapeDataString(x.Value?.ToString() ?? "")));
            var result = await api.Get("/api/reports/preview?" + query); ReadState(result); RenderReportPreview(preview, result.Data); message.Text = result.Offline ? "Предпросмотр из локального кеша; данные могут быть устаревшими." : "Предпросмотр сформирован по актуальным данным.";
        });
        export.Click += async (_, _) => await Run(async () =>
        {
            var response = await api.Mutate("POST", "/api/reports/export", Payload());
            var path = await api.Download(response.Text("url"), response.Text("filename", "report." + format.SelectedItem));
            message.Text = "Сохранено: " + path; Toast("Отчёт сохранён"); Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
        });
    }
    private void RenderReportPreview(Panel preview, JsonNode report)
    {
        preview.Children.Clear(); preview.Children.Add(Ui.Text(report.Text("title", "Отчёт"), 22, true));
        var summary = (report["summary"]?["metrics"] ?? report["summary"]) as JsonObject ?? new JsonObject();
        var bars = new JsonArray();
        var summaryLine = new WrapPanel { Margin = new Thickness(0, 0, 0, 12) }; preview.Children.Add(summaryLine);
        foreach (var (key, value) in summary)
        {
            if (value is JsonArray or JsonObject) continue;
            var label = Ui.Text(ReportMetricLabel(key) + ": " + value, 12); label.Margin = new Thickness(0, 0, 24, 8); summaryLine.Children.Add(label);
            if (decimal.TryParse(value?.ToString(), NumberStyles.Any, CultureInfo.InvariantCulture, out var number)) bars.Add(new JsonObject { ["label"] = key, ["value"] = number });
        }
        var metric = report.Text("type") switch { "downtime" => "hours", "schedule" => "completed", "team-efficiency" => "completed", "material-usage" => "cost", _ => "" };
        if (metric.Length > 0)
        {
            var values = report["rows"].Rows().Take(12).Select(x => (JsonNode)new JsonObject { ["label"] = x.Text("label"), ["value"] = x[metric]?.DeepClone() ?? JsonValue.Create(0) });
            preview.Children.Add(RenderBars(report.Text("type") == "downtime" ? "Простой по оборудованию, ч" : report.Text("type") == "material-usage" ? "Стоимость материалов" : "Выполнено", new JsonArray(values.ToArray())));
        }
        else if (report["charts"] is JsonArray charts && charts.Count > 0)
        {
            foreach (var chart in charts.Rows()) preview.Children.Add(RenderBars(chart.Text("title", "Показатели отчёта"), chart["items"]));
        }
        else if (bars.Count > 0) preview.Children.Add(RenderBars("Показатели отчёта", bars));
        else
        {
            var rows = report["rows"].Rows().ToList(); var counts = rows.GroupBy(x => x.Text("Status", x.Text("WorkshopName", "Записей"))).Select(x => (JsonNode)new JsonObject { ["label"] = x.Key, ["value"] = x.Count() });
            preview.Children.Add(RenderBars("Состав отчёта", new JsonArray(counts.ToArray())));
        }
        var fields = report["columns"].Rows().Select(x => (JsonNode)new JsonObject { ["name"] = x.Text("key"), ["label"] = x.Text("label") });
        var table = MakeTable(report["rows"].Rows(), fields); table.Grid.MaxHeight = 480; preview.Children.Add(table.Grid);
    }
    private static string ReportMetricLabel(string key) => key switch
    {
        "equipment" => "Оборудование", "repair_equipment" => "В ремонте", "open_orders" => "Активные заявки", "overdue" => "Просроченные заявки", "low_stock" => "Дефицитные материалы", "downtime_hours" => "Простой, ч", "today_orders" => "Заявки сегодня", "avg_completion_hours" => "Среднее выполнение, ч", "completed_orders" => "Выполнено заявок", "material_cost" => "Стоимость материалов", "rows" => "Записей", _ => CommonLabel(key)
    };
}
