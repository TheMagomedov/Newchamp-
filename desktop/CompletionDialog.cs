namespace Toir.Desktop;

public partial class MainWindow
{
    private async Task<bool> CompleteOrder(int id, Window owner)
    {
        try
        {
            lookups = (await api.Get("/api/lookups")).Data;
            var already = (await api.Get($"/api/work-orders/{id}/materials")).Data.Rows().Select(x => x.Int("MaterialId")).ToHashSet();
            var window = new Window { Owner = owner, Title = "Заявки / Завершение работ", Width = 750, Height = 700, WindowStartupLocation = WindowStartupLocation.CenterOwner, Style = (Style)Application.Current.FindResource(typeof(Window)) }; Ui.Fit(window);
            var root = new DockPanel { Margin = new Thickness(24) }; window.Content = root;
            var bottom = new StackPanel(); DockPanel.SetDock(bottom, Dock.Bottom); root.Children.Add(bottom);
            var error = Ui.Text(""); error.Foreground = Brushes.Firebrick; bottom.Children.Add(error);
            var progress = new ProgressBar { IsIndeterminate = true, Height = 4, Visibility = Visibility.Collapsed, Margin = new Thickness(0, 0, 0, 10) }; bottom.Children.Add(progress);
            var buttons = new WrapPanel(); bottom.Children.Add(buttons);
            var submit = new Button { Content = "Завершить и списать атомарно" }; buttons.Children.Add(submit); buttons.Children.Add(Ui.Button("Отмена", (_, _) => window.Close(), true));
            var body = new StackPanel(); root.Children.Add(new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto });
            body.Children.Add(Ui.Text("ТОиР / Заявки / Завершение", 22, true));
            body.Children.Add(Ui.Text("Отчёт и дополнительные материалы сохраняются одной серверной транзакцией. Заявка должна находиться в работе.", 13));
            body.Children.Add(Ui.Text("Отчёт о выполненных работах *"));
            var report = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 95, Margin = new Thickness(0, 0, 0, 12) }; body.Children.Add(report);
            body.Children.Add(Ui.Text("Фактическое окончание UTC (пусто — время сервера)"));
            var end = new TextBox { ToolTip = "2027-02-10T10:30:00", Margin = new Thickness(0, 0, 0, 14) }; body.Children.Add(end);
            var selected = new List<JsonNode>();
            if (api.User.Text("Role") != "engineer")
            {
                body.Children.Add(Ui.Text("Дополнительные материалы", 17, true));
                body.Children.Add(Ui.Text("Уже списанные материалы не добавляйте повторно. Остаток и количество окончательно проверяет сервер.", 12));
                var line = new WrapPanel { Margin = new Thickness(0, 0, 0, 10) }; body.Children.Add(line);
                var material = new ComboBox { Width = 280, DisplayMemberPath = "Label", SelectedValuePath = "Value", ItemsSource = lookups["materials"].Rows().Where(x => !already.Contains(x.Int("id"))).Select(x => new EditorDialog.Choice(x.Text("id"), x.Text("label"))).ToList(), Margin = new Thickness(0, 0, 10, 0) }; line.Children.Add(material);
                var quantity = new TextBox { Width = 90, Text = "1", ToolTip = "Количество", Margin = new Thickness(0, 0, 10, 0) }; line.Children.Add(quantity);
                var list = new ListBox { Height = 150, DisplayMemberPath = "Label", Margin = new Thickness(0, 0, 0, 10) }; body.Children.Add(list);
                void Refresh() => list.ItemsSource = selected.Select(x => new CompletionRow(x, x.Text("Label") + " · " + x.Text("Quantity"))).ToList();
                line.Children.Add(Ui.Button("Добавить", (_, _) =>
                {
                    if (!int.TryParse(material.SelectedValue?.ToString(), out var materialId) || !decimal.TryParse(quantity.Text.Replace(',', '.'), NumberStyles.Number, CultureInfo.InvariantCulture, out var amount) || amount <= 0) { error.Text = "Выберите материал и положительное количество."; return; }
                    if (selected.Any(x => x.Int("MaterialId") == materialId)) { error.Text = "Этот материал уже добавлен."; return; }
                    selected.Add(new JsonObject { ["MaterialId"] = materialId, ["Quantity"] = amount, ["Label"] = ((EditorDialog.Choice)material.SelectedItem).Label }); Refresh(); error.Text = "";
                }, true));
                body.Children.Add(Ui.Button("Убрать выбранный материал", (_, _) => { if (list.SelectedItem is CompletionRow row) { selected.Remove(row.Item); Refresh(); } }, true));
            }
            submit.Click += async (_, _) =>
            {
                submit.IsEnabled = false; progress.Visibility = Visibility.Visible;
                try
                {
                    if (string.IsNullOrWhiteSpace(report.Text)) throw new InvalidOperationException("Заполните отчёт о работах.");
                    var payload = new JsonObject { ["completion_report"] = report.Text.Trim(), ["materials"] = new JsonArray(selected.Select(x => (JsonNode)new JsonObject { ["MaterialId"] = x.Int("MaterialId"), ["Quantity"] = x["Quantity"]!.DeepClone() }).ToArray()) };
                    if (end.Text.Trim().Length > 0)
                    {
                        if (!DateTime.TryParse(end.Text.Trim(), CultureInfo.InvariantCulture, DateTimeStyles.AllowWhiteSpaces, out var date)) throw new InvalidOperationException("Введите окончание в формате yyyy-MM-ddTHH:mm:ss.");
                        payload["actual_end"] = date.ToString("s");
                    }
                    if (await Write("POST", $"/api/work-orders/{id}/complete", payload, window)) window.DialogResult = true;
                }
                catch (Exception e) { error.Text = e.Message; }
                finally { submit.IsEnabled = true; progress.Visibility = Visibility.Collapsed; }
            };
            return window.ShowDialog() == true;
        }
        catch (Exception e) { Notify(e.Message); return false; }
    }
    private record CompletionRow(JsonNode Item, string Label);
}
