namespace Toir.Desktop;

// Учебный модуль: реестры, поиск, фильтры, сортировка и сохранение записей.
public partial class MainWindow
{
    private readonly Dictionary<string, string> extraFilters = [];
    private string sortBy = "Id", sortDir = "asc";
    private int pageSize = 25;
    private TextBox? searchBox;
    private void RenderResource(JsonNode resource, JsonNode data)
    {
        ContentHost.Children.Clear(); var root = new DockPanel(); ContentHost.Children.Add(root);
        var toolbar = new WrapPanel { Margin = new Thickness(0, 0, 0, 14) }; DockPanel.SetDock(toolbar, Dock.Top); root.Children.Add(toolbar);
        var query = new TextBox { Text = search, Width = 225, Margin = new Thickness(0, 0, 8, 0), ToolTip = "Поиск по записям" }; toolbar.Children.Add(query);
        searchBox = query;
        async Task Find() { search = query.Text.Trim(); page = 1; await LoadCurrent(); }
        query.KeyDown += async (_, e) => { if (e.Key == Key.Enter) await Find(); };
        toolbar.Children.Add(Ui.Button("Найти", async (_, _) => await Find(), true));
        toolbar.Children.Add(Ui.Button("Сбросить", async (_, _) => { search = statusFilter = ""; extraFilters.Clear(); page = 1; await LoadCurrent(); }, true));
        var statusField = resource["fields"].Rows().FirstOrDefault(f => f.Text("name") == "Status");
        if (statusField?["options"] is JsonArray options)
        {
            var filter = new ComboBox { Width = 145, Margin = new Thickness(0, 0, 8, 0) };
            filter.Items.Add("Все статусы"); foreach (var value in options.Rows()) filter.Items.Add(value is JsonObject ? value.Text("value") : value.ToString());
            filter.SelectedItem = statusFilter.Length > 0 ? statusFilter : "Все статусы";
            filter.SelectionChanged += async (_, _) => { statusFilter = filter.SelectedIndex > 0 ? filter.SelectedItem?.ToString() ?? "" : ""; page = 1; await LoadCurrent(); }; toolbar.Children.Add(filter);
        }
        AddFilters(toolbar, resource);
        var table = MakeTable(data["items"].Rows(), resource["fields"].Rows()); WireServerSort(table.Grid);
        void RowAction(string title, Func<JsonNode, Task> action)
        {
            var button = Ui.Button(title, async (_, _) => { if (table.Selected() is { } row) await action(row); }, true);
            button.IsEnabled = false; toolbar.Children.Add(button);
            table.Grid.SelectionChanged += (_, _) => button.IsEnabled = table.Selected() is not null;
        }
        bool hasDetails = section is "equipment" or "work-orders" or "teams";
        async Task OpenRow() { if (table.Selected() is { } row) { if (hasDetails) await ShowDetails(resource.Text("key"), row.Int("Id")); else if (resource.Bool("canWrite")) await Edit(resource, row); } }
        table.Grid.MouseDoubleClick += async (_, e) => { if (ItemsControl.ContainerFromElement(table.Grid, e.OriginalSource as DependencyObject) is DataGridRow) await OpenRow(); };
        table.Grid.PreviewKeyDown += async (_, e) => { if (e.Key == Key.Enter) { e.Handled = true; await OpenRow(); } };
        if (resource.Bool("canWrite"))
        {
            toolbar.Children.Add(Ui.Button("+ Добавить", async (_, _) => await Edit(resource, null)));
            RowAction("Изменить", row => Edit(resource, row));
        }
        if (resource.Bool("canDelete")) RowAction("Удалить", async row =>
        {
            if (MessageBox.Show(this, "Удалить выбранную запись? Связанные записи защищены сервером.", "Подтверждение", MessageBoxButton.YesNo, MessageBoxImage.Question) == MessageBoxResult.Yes)
                if (await Write("DELETE", $"/api/{resource.Text("key")}/{row.Int("Id")}", null)) await LoadCurrent();
        });
        if (section is "equipment" or "work-orders") RowAction("История", row => History(resource.Text("key"), row.Int("Id")));
        if (section == "work-orders") RowAction("Статус и материалы", row => { OrderActions(row, api.User.Text("Role") is "admin" or "engineer" or "master" or "member"); return Task.CompletedTask; });
        if (hasDetails) RowAction("Подробнее", row => ShowDetails(resource.Text("key"), row.Int("Id")));
        var footer = new DockPanel { Margin = new Thickness(0, 12, 0, 0) }; DockPanel.SetDock(footer, Dock.Bottom); root.Children.Add(footer);
        footer.Children.Add(Ui.Text($"Всего: {data.Int("total")}  •  Страница {page} из {Math.Max(1, (int)Math.Ceiling(data.Int("total") / (double)pageSize))}", 12));
        var size = new ComboBox { ItemsSource = new[] { 25, 50, 100 }, SelectedItem = pageSize, Width = 72, Margin = new Thickness(10, 0, 10, 0) }; size.SelectionChanged += async (_, _) => { pageSize = (int)size.SelectedItem; page = 1; await LoadCurrent(); }; footer.Children.Add(size);
        var paging = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right }; DockPanel.SetDock(paging, Dock.Right); footer.Children.Add(paging);
        var previous = Ui.Button("← Назад", async (_, _) => { page--; await LoadCurrent(); }, true); previous.IsEnabled = page > 1; paging.Children.Add(previous);
        var next = Ui.Button("Далее →", async (_, _) => { page++; await LoadCurrent(); }, true); next.IsEnabled = page * pageSize < data.Int("total"); paging.Children.Add(next);
        root.Children.Add(table.Grid);
        if (data.Int("total") == 0) Notify("По выбранным условиям записей нет. Измените поиск или добавьте новую запись, если это разрешено вашей роли.");
    }
    private async Task Edit(JsonNode resource, JsonNode? record)
    {
        try
        {
            // Lookups refresh when opening a form so recently created references become available.
            lookups = (await api.Get("/api/lookups")).Data;
            var fields = resource["fields"]!.DeepClone();
            if (record is not null && resource.Text("key") == "work-orders")
                foreach (var field in fields.Rows().Where(f => f.Text("name") == "Status")) field["readOnly"] = true;
            var dialog = new EditorDialog((record is null ? "Добавить • " : "Изменить • ") + resource.Text("label"), fields.Rows(), lookups, record) { Owner = this };
            dialog.SaveAsync = payload => Write(record is null ? "POST" : "PUT", $"/api/{resource.Text("key")}" + (record is null ? "" : "/" + record.Int("Id")), payload, dialog);
            if (dialog.ShowDialog() == true) await LoadCurrent();
        }
        catch (Exception e) { Notify(e.Message); }
    }
    private async Task<bool> Write(string method, string path, JsonNode? payload, Window? owner = null)
    {
        var requestId = Guid.NewGuid().ToString();
        try { await api.Mutate(method, path, payload, requestId); Notify(null); Toast("Изменения сохранены"); StatusText.Text = "Изменения сохранены"; return true; }
        catch (OfflineException e)
        {
            if (payload is JsonObject obj && obj.Any(kv => kv.Key.Equals("Password", StringComparison.OrdinalIgnoreCase)))
            {
                MessageBox.Show(owner ?? this, e.Message + "\nИзменения с паролем нельзя сохранять в локальную очередь. Повторите операцию после подключения.", "Нет подключения", MessageBoxButton.OK, MessageBoxImage.Warning); return false;
            }
            if (MessageBox.Show(owner ?? this, e.Message + "\n\nДобавить действие в локальную очередь? " + (AutoSync ? "Автоотправка включена: после восстановления связи запрос будет отправлен автоматически." : "Автоотправка выключена: нажмите «Повторить» вручную или включите её в очереди.") + " Тот же ключ запроса защищает от дублирования.", "Нет подключения", MessageBoxButton.YesNo, MessageBoxImage.Warning) == MessageBoxResult.Yes)
            {
                api.Enqueue(new(requestId, method, path, payload?.DeepClone(), DateTime.Now.ToString("g"))); QueueButton.Content = $"Очередь: {api.Queue().Count}"; return true;
            }
            return false;
        }
        catch (Exception e)
        {
            if (MessageBox.Show(owner ?? this, e.Message + "\n\nПовторить попытку с теми же данными?", "Изменения не сохранены", MessageBoxButton.OKCancel, MessageBoxImage.Warning) == MessageBoxResult.OK)
            { try { await api.Mutate(method, path, payload, requestId); Toast("Изменения сохранены"); return true; } catch (Exception retry) { MessageBox.Show(owner ?? this, retry.Message, "Повтор не выполнен"); } }
            return false;
        }
    }
    private async Task History(string resource, int id)
    {
        try
        {
            var result = await api.Get($"/api/{resource}/{id}/history");
            var dialog = new Window { Owner = this, Title = $"История #{id}", Width = 980, Height = 500, WindowStartupLocation = WindowStartupLocation.CenterOwner };
            Ui.Fit(dialog);
            var grid = MakeTable(result.Data.Rows()).Grid; grid.Margin = new Thickness(20); dialog.Content = grid; dialog.ShowDialog();
        }
        catch (Exception e) { Notify(e.Message); }
    }
    private string FilterQuery() => string.Concat(extraFilters.Where(x => x.Value.Length > 0).Select(x => "&" + x.Key + "=" + Uri.EscapeDataString(x.Value)));
    private void AddFilters(Panel panel, JsonNode resource)
    {
        var shop = ChoiceBox("workshop_id", "Все цеха", lookups["workshops"].Rows().Select(x => new EditorDialog.Choice(x.Text("id"), x.Text("label")))); panel.Children.Add(shop);
        foreach (var (field, query) in new[] { ("Priority", "priority"), ("Type", "type") })
        {
            var options = resource["fields"].Rows().FirstOrDefault(x => x.Text("name") == field)?["options"];
            if (options is not null) panel.Children.Add(ChoiceBox(query, field == "Priority" ? "Любой приоритет" : "Все типы", options.Rows().Select(x => new EditorDialog.Choice(x.ToString(), x.ToString()))));
        }
        if (section is "equipment" or "materials")
        {
            var key = section == "equipment" ? "model" : "location";
            var text = new TextBox { Text = extraFilters.GetValueOrDefault(key, ""), Width = 145, Margin = new Thickness(0, 4, 8, 4), ToolTip = key == "model" ? "Модель оборудования" : "Склад / место хранения" };
            async Task ApplyText() { extraFilters[key] = text.Text.Trim(); page = 1; await LoadCurrent(); }
            text.KeyDown += async (_, e) => { if (e.Key == Key.Enter) await ApplyText(); }; panel.Children.Add(text);
            panel.Children.Add(Ui.Button(key == "model" ? "По модели" : "По складу", async (_, _) => await ApplyText(), true));
        }
        if (section == "work-orders")
        {
            foreach (var key in new[] { "date_from", "date_to" })
            {
                var picker = new DatePicker { Width = 145, ToolTip = key == "date_from" ? "Создано с" : "Создано по", Margin = new Thickness(0, 4, 8, 4), SelectedDate = DateTime.TryParse(extraFilters.GetValueOrDefault(key), out var date) ? date : null };
                picker.SelectedDateChanged += async (_, _) => { extraFilters[key] = picker.SelectedDate?.ToString("yyyy-MM-dd") ?? ""; page = 1; await LoadCurrent(); }; panel.Children.Add(picker);
            }
        }
    }
    private ComboBox ChoiceBox(string key, string empty, IEnumerable<EditorDialog.Choice> choices)
    {
        var items = new List<EditorDialog.Choice> { new("", empty) }; items.AddRange(choices);
        var box = new ComboBox { Width = 155, Margin = new Thickness(0, 4, 8, 4), DisplayMemberPath = "Label", SelectedValuePath = "Value", ItemsSource = items, SelectedValue = extraFilters.GetValueOrDefault(key, "") };
        box.SelectionChanged += async (_, _) => { extraFilters[key] = box.SelectedValue?.ToString() ?? ""; page = 1; await LoadCurrent(); }; return box;
    }
    private void WireServerSort(DataGrid grid)
    {
        grid.Sorting += async (_, e) =>
        {
            e.Handled = true; var field = e.Column.SortMemberPath.Trim('[', ']');
            if (!meta["resources"].Rows().FirstOrDefault(x => x.Text("key") == section)?["fields"].Rows().Any(x => x.Text("name") == field) ?? true) return;
            sortDir = sortBy == field && sortDir == "asc" ? "desc" : "asc"; sortBy = field; await LoadCurrent();
        };
    }
}
