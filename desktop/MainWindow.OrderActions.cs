namespace Toir.Desktop;

// Учебный модуль: переходы статусов заявок и работа с расходом материалов.
public partial class MainWindow
{
    private void OrderActions(JsonNode order, bool canWrite)
    {
        var id = order.Int("Id"); var window = new Window { Owner = this, Title = $"Заказ #{id}", Width = 970, Height = 650, WindowStartupLocation = WindowStartupLocation.CenterOwner };
        Ui.Fit(window);
        var root = new DockPanel { Margin = new Thickness(23) }; window.Content = root;
        var heading = new StackPanel(); heading.Children.Add(Ui.Text($"Заказ #{id} · {order.Text("Status")}", 23, true)); heading.Children.Add(Ui.Text(order.Text("Description"))); DockPanel.SetDock(heading, Dock.Top); root.Children.Add(heading);
        var actions = new WrapPanel { Margin = new Thickness(0, 12, 0, 16) }; DockPanel.SetDock(actions, Dock.Top); root.Children.Add(actions);
        var content = new Grid(); root.Children.Add(content); List<JsonNode> materials = [];
        TableView? table = null;
        async Task Reload()
        {
            try { materials = (await api.Get($"/api/work-orders/{id}/materials")).Data.Rows().ToList(); table = MakeTable(materials); content.Children.Clear(); content.Children.Add(table.Grid); }
            catch (Exception e) { MessageBox.Show(window, e.Message, "Материалы заказа"); }
        }
        if (canWrite)
        {
            actions.Children.Add(Ui.Button("Завершить работы", async (_, _) => { if (await CompleteOrder(id, window)) { await LoadCurrent(); window.Close(); } }));
            actions.Children.Add(Ui.Button("Сменить статус", async (_, _) =>
            {
                var fields = JsonNode.Parse("""[{"name":"status","label":"Новый статус","type":"select","required":true,"options":["создана","назначена","в работе","ожидает материалов","выполнена","закрыта","отменена"]},{"name":"team_id","label":"Бригада","type":"number","lookup":"teams"},{"name":"actual_start","label":"Фактическое начало (UTC)","type":"datetime"},{"name":"actual_end","label":"Фактическое окончание (UTC)","type":"datetime"},{"name":"completion_report","label":"Отчёт о выполнении","type":"textarea"}]""")!;
                var initial = new JsonObject { ["status"] = order["Status"]?.DeepClone(), ["team_id"] = order["TeamId"]?.DeepClone(), ["actual_start"] = order["ActualStart"]?.DeepClone(), ["actual_end"] = order["ActualEnd"]?.DeepClone(), ["completion_report"] = order["CompletionReport"]?.DeepClone() };
                var editor = new EditorDialog("Переход статуса", fields.Rows(), lookups, initial) { Owner = window };
                editor.SaveAsync = payload => Write("POST", $"/api/work-orders/{id}/transition", TransitionPayload.Build(payload, order), editor);
                if (editor.ShowDialog() == true) { await LoadCurrent(); window.Close(); }
            }));
            async Task Material(bool edit)
            {
                var selected = edit ? table?.Selected() : null;
                if (edit && selected is null) { MessageBox.Show(window, "Выберите материал."); return; }
                var fields = JsonNode.Parse("""[{"name":"MaterialId","label":"Материал","type":"number","lookup":"materials","required":true},{"name":"Quantity","label":"Количество","type":"number","required":true},{"name":"Comment","label":"Комментарий","type":"textarea"}]""")!;
                if (edit) fields[0]!["readOnly"] = true;
                var editor = new EditorDialog(edit ? "Изменить расход" : "Добавить расход", fields.Rows(), lookups, selected) { Owner = window };
                editor.SaveAsync = payload => Write(edit ? "PUT" : "POST", $"/api/work-orders/{id}/materials" + (edit ? "/" + selected.Int("MaterialId") : ""), payload, editor);
                if (editor.ShowDialog() == true) await Reload();
            }
            if (api.User.Text("Role") is "admin" or "master" or "member")
            {
              actions.Children.Add(Ui.Button("+ Материал", async (_, _) => await Material(false), true));
              actions.Children.Add(Ui.Button("Изменить расход", async (_, _) => await Material(true), true));
              actions.Children.Add(Ui.Button("Удалить расход", async (_, _) =>
            {
                if (table?.Selected() is not { } selected) { MessageBox.Show(window, "Выберите материал."); return; }
                if (MessageBox.Show(window, "Удалить расход и вернуть количество на склад?", "Подтверждение", MessageBoxButton.YesNo) == MessageBoxResult.Yes)
                    if (await Write("DELETE", $"/api/work-orders/{id}/materials/{selected.Int("MaterialId")}", null, window)) await Reload();
              }, true));
            }
        }
        actions.Children.Add(Ui.Button("Обновить", async (_, _) => await Reload(), true));
        window.Loaded += async (_, _) => await Reload(); window.ShowDialog();
    }
}
