namespace Toir.Desktop;

// Учебный модуль: месячный календарь ТО и создание заявки из графика.
public partial class MainWindow
{
    private DateTime calendarMonth = new(DateTime.Today.Year, DateTime.Today.Month, 1);
    private DateTime? calendarDay;
    private async Task<List<JsonNode>> AllPages(string resource, string query)
    {
        var session = sessionRevision; var revision = loadRevision;
        var rows = new List<JsonNode>();
        for (var p = 1; p <= 100; p++)
        {
            var result = await api.Get($"/api/{resource}?page={p}&page_size=100" + query);
            if (!ready || session != sessionRevision || revision != loadRevision) return rows;
            ReadState(result);
            var items = result.Data["items"].Rows().ToList(); rows.AddRange(items);
            if (rows.Count >= result.Data.Int("total") || items.Count == 0) return rows;
        }
        throw new InvalidOperationException("Слишком много записей. Сузьте период/цех (лимит 10 000).");
    }
    private async Task LoadSchedule(int revision)
    {
        var start = calendarMonth.ToString("yyyy-MM-dd"); var end = calendarMonth.AddMonths(1).AddDays(-1).ToString("yyyy-MM-dd");
        var rows = await AllPages("schedule", $"&date_from={start}&date_to={end}&sort_by=PlannedAt&sort_dir=asc");
        if (revision == loadRevision && section == "schedule") RenderSchedule(rows);
    }
    private void RenderSchedule(List<JsonNode> rows)
    {
        ContentHost.Children.Clear(); var root = new DockPanel(); ContentHost.Children.Add(root);
        var top = new StackPanel(); DockPanel.SetDock(top, Dock.Top); root.Children.Add(top);
        var nav = new WrapPanel { Margin = new Thickness(0, 0, 0, 10) }; top.Children.Add(nav);
        nav.Children.Add(Ui.Button("←", async (_, _) => { calendarMonth = calendarMonth.AddMonths(-1); calendarDay = null; await LoadCurrent(); }, true));
        nav.Children.Add(Ui.Text(calendarMonth.ToString("MMMM yyyy", CultureInfo.GetCultureInfo("ru-RU")), 21, true));
        nav.Children.Add(Ui.Button("→", async (_, _) => { calendarMonth = calendarMonth.AddMonths(1); calendarDay = null; await LoadCurrent(); }, true));
        nav.Children.Add(Ui.Button("Весь месяц", (_, _) => { calendarDay = null; RenderSchedule(rows); }, true));
        var resource = meta["resources"].Rows().First(r => r.Text("key") == "schedule");
        if (resource.Bool("canWrite")) nav.Children.Add(Ui.Button("+ Запись ТО", async (_, _) => await Edit(resource, null)));
        top.Children.Add(Ui.Text("Красный — просрочено; жёлтый — ближайшие 3 дня. Нажмите дату для фильтрации.", 11));
        var calendar = new System.Windows.Controls.Primitives.UniformGrid { Columns = 7, Margin = new Thickness(0, 0, 0, 12) };
        foreach (var name in new[] { "ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС" }) calendar.Children.Add(new TextBlock { Text = name, HorizontalAlignment = HorizontalAlignment.Center, Foreground = Brushes.SlateGray, Margin = new Thickness(0, 0, 0, 6) });
        int offset = ((int)calendarMonth.DayOfWeek + 6) % 7;
        for (int n = 0; n < 42; n++)
        {
            var day = calendarMonth.AddDays(n - offset); var scheduled = rows.Where(r => DateTime.TryParse(r.Text("PlannedAt"), out var d) && d.Date == day.Date).ToList();
            var content = new StackPanel(); content.Children.Add(new TextBlock { Text = day.Day.ToString(), FontWeight = FontWeights.SemiBold });
            content.Children.Add(new TextBlock { Text = scheduled.Count > 0 ? $"{scheduled.Count} ТО" : " ", FontSize = 10 });
            var button = new Button { Content = content, Margin = new Thickness(2), Padding = new Thickness(7, 3, 7, 3), MinHeight = 37, Background = scheduled.Count > 0 ? RowColor(scheduled.OrderBy(r => r.Text("PlannedAt")).First()) : Brushes.White, Foreground = day.Month == calendarMonth.Month ? Brushes.DarkSlateGray : Brushes.Silver, BorderThickness = new Thickness(calendarDay == day ? 2 : 0), BorderBrush = Brushes.Teal };
            button.Click += (_, _) => { calendarDay = day; RenderSchedule(rows); }; calendar.Children.Add(button);
        }
        top.Children.Add(calendar);
        var filtered = calendarDay is null ? rows : rows.Where(r => DateTime.TryParse(r.Text("PlannedAt"), out var d) && d.Date == calendarDay.Value.Date).ToList();
        var actions = new WrapPanel { Margin = new Thickness(0, 0, 0, 8) }; top.Children.Add(actions);
        actions.Children.Add(Ui.Text(calendarDay?.ToString("dd.MM.yyyy") ?? $"Весь месяц · {filtered.Count} записей", 13, true));
        var table = MakeTable(filtered, resource["fields"].Rows());
        if (resource.Bool("canWrite"))
        {
            actions.Children.Add(Ui.Button("Изменить", async (_, _) => { if (table.Selected() is { } row) await Edit(resource, row); }, true));
            actions.Children.Add(Ui.Button("Создать заявку", async (_, _) => { if (table.Selected() is { } row) await CreateFromSchedule(row); else Notify("Выберите запись графика."); }));
        }
        root.Children.Add(table.Grid);
    }
    private async Task CreateFromSchedule(JsonNode row)
    {
        try
        {
            lookups = (await api.Get("/api/lookups")).Data;
            var equipment = (await api.Get($"/api/equipment/{row.Int("EquipmentId")}")).Data;
            var master = lookups["masters"].Rows().FirstOrDefault(x => x.Int("workshop_id") == equipment.Int("WorkshopId"));
            var fields = JsonNode.Parse("""[{"name":"master_id","label":"Ответственный мастер","required":true,"lookup":"masters"},{"name":"planned_start","label":"Плановое начало (UTC)","type":"datetime","required":true},{"name":"planned_hours","label":"Плановая длительность, ч","type":"number"},{"name":"priority","label":"Приоритет","options":["низкий","средний","высокий","критический"]}]""")!;
            var originalDate = DateTime.TryParse(row.Text("PlannedAt"), out var planned) ? planned : DateTime.UtcNow;
            var seed = new JsonObject { ["master_id"] = master?["id"]?.DeepClone(), ["planned_start"] = (originalDate < DateTime.UtcNow ? DateTime.UtcNow.AddMinutes(5) : originalDate).ToString("s"), ["planned_hours"] = 1, ["priority"] = "средний" };
            var dialog = new EditorDialog("График ТО / Создать заявку", fields.Rows(), lookups, seed) { Owner = this };
            dialog.SaveAsync = payload => Write("POST", $"/api/schedule/{row.Int("Id")}/create-order", payload, dialog);
            if (dialog.ShowDialog() == true) await LoadCurrent();
        }
        catch (Exception e) { Notify(e.Message); }
    }
}
