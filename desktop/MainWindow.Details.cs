namespace Toir.Desktop;

// Учебный модуль: карточки оборудования, заявок и бригад со связанной историей.
public partial class MainWindow
{
    private Task ShowOrderDetails(int id) => ShowDetails("work-orders", id);
    private Window DetailWindow(string title, out DockPanel root)
    {
        var window = new Window { Owner = this, Title = title, Width = 1080, Height = 700, WindowStartupLocation = WindowStartupLocation.CenterOwner, Style = (Style)Application.Current.FindResource(typeof(Window)) }; Ui.Fit(window);
        root = new DockPanel { Margin = new Thickness(22) }; window.Content = root;
        var heading = Ui.Text("ТОиР / " + title, 21, true); DockPanel.SetDock(heading, Dock.Top); root.Children.Add(heading); return window;
    }
    private TabItem TableTab(string title, IEnumerable<JsonNode> rows) => new() { Header = title, Content = MakeTable(rows).Grid };
    private TabItem InfoTab(JsonNode row)
    {
        var body = new StackPanel { Margin = new Thickness(18) };
        if (row is JsonObject obj) foreach (var (key, value) in obj.Where(x => x.Value is not (JsonArray or JsonObject) && x.Key is not ("Version" or "PasswordHash"))) body.Children.Add(Ui.Text(CommonLabel(key) + ": " + value));
        return new TabItem { Header = "Основная информация", Content = new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto } };
    }
    private async Task ShowDetails(string resource, int id)
    {
        var session = sessionRevision;
        try
        {
            var result = await api.Get($"/api/{resource}/{id}" + (resource == "equipment" ? "/details" : ""));
            if (!ready || session != sessionRevision) return;
            ReadState(result);
            var record = result.Data;
            var label = resource switch { "equipment" => "Оборудование", "teams" => "Бригады", _ => "Заявки" };
            var title = resource == "work-orders" ? record.Text("DisplayNumber", record.Text("Number")) : record.Text("Name");
            var window = DetailWindow(label + " / " + title, out var root);
            var actions = new WrapPanel { Margin = new Thickness(0, 10, 0, 10) }; DockPanel.SetDock(actions, Dock.Top); root.Children.Add(actions);
            var canAct = api.User.Text("Role") is "admin" or "engineer" or "master" or "member";
            if (resource == "equipment" && meta["resources"].Rows().FirstOrDefault(r => r.Text("key") == "work-orders").Bool("canWrite"))
                actions.Children.Add(Ui.Button("Создать заявку", async (_, _) => await CreateOrderForEquipment(record, window)));
            if (resource == "work-orders" && canAct)
                actions.Children.Add(Ui.Button("Действия заявки и материалы", (_, _) => OrderActions(record, canAct)));
            if (resource == "teams")
                actions.Children.Add(Ui.Text($"Активных заявок: {record["workload"].Text("active", "0")}   •   Плановая загрузка: {record["workload"].Text("planned_hours", "0")} ч", 17, true));
            var tabs = new TabControl(); tabs.Items.Add(InfoTab(record));
            if (resource == "work-orders") tabs.Items.Add(TimelineTab(record));
            var sections = resource switch
            {
                "equipment" => new[] { ("История заявок", "orders"), ("История ТО", "schedule"), ("Изменения", "history") },
                "teams" => new[] { ("Состав", "members"), ("Активные заявки", "active_orders") },
                _ => new[] { ("Связанные материалы", "materials") }
            };
            foreach (var (name, key) in sections) tabs.Items.Add(TableTab(name, record[key].Rows()));
            root.Children.Add(tabs); window.ShowDialog();
        }
        catch (Exception e) { if (ready && session == sessionRevision) Notify(e.Message); }
    }
    private async Task CreateOrderForEquipment(JsonNode equipment, Window owner)
    {
        try
        {
            lookups = (await api.Get("/api/lookups")).Data;
            var resource = meta["resources"].Rows().First(r => r.Text("key") == "work-orders");
            if (!resource.Bool("canWrite")) throw new InvalidOperationException("Нет права создавать заявки.");
            var master = lookups["masters"].Rows().FirstOrDefault(x => x.Int("workshop_id") == equipment.Int("WorkshopId"));
            var seed = new JsonObject { ["EquipmentId"] = equipment.Int("Id"), ["MasterId"] = master?["id"]?.DeepClone(), ["Type"] = "плановая", ["Priority"] = "средний", ["Status"] = "создана", ["PlannedStart"] = DateTime.UtcNow.AddHours(1).ToString("s"), ["PlannedEnd"] = DateTime.UtcNow.AddHours(2).ToString("s") };
            var editor = new EditorDialog("Оборудование / Новая заявка", resource["fields"].Rows(), lookups, seed) { Owner = owner };
            editor.SaveAsync = payload => Write("POST", "/api/work-orders", payload, editor); editor.ShowDialog();
        }
        catch (Exception e) { MessageBox.Show(owner, e.Message, "Создание заявки"); }
    }
    private TabItem TimelineTab(JsonNode record)
    {
        var timeline = new StackPanel { Margin = new Thickness(18) };
        foreach (var change in record["history"].Rows())
        {
            var line = new StackPanel();
            line.Children.Add(Ui.Text("● " + change.Text("ChangedAt") + "  " + change.Text("OldStatus") + " → " + change.Text("NewStatus"), 15, true));
            line.Children.Add(Ui.Text(change.Text("Comment") + " " + change.Text("ChangedByName"), 12)); timeline.Children.Add(Ui.Card(line));
        }
        if (timeline.Children.Count == 0) timeline.Children.Add(Ui.Text("История статусов пока пуста."));
        return new TabItem { Header = "Таймлайн статусов", Content = new ScrollViewer { Content = timeline, VerticalScrollBarVisibility = ScrollBarVisibility.Auto } };
    }
}
