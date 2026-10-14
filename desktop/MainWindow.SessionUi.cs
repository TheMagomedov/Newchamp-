namespace Toir.Desktop;

// Учебный модуль: настройки, горячие клавиши, уведомления и очередь офлайн-запросов.
public partial class MainWindow
{
    private JsonNode notificationData = new JsonObject();
    private readonly DispatcherTimer sync = new() { Interval = TimeSpan.FromSeconds(10) };
    private bool syncing;
    private int toastRevision;
    private JsonObject Preferences => LocalStore.Read(api.UserFile("preferences")) as JsonObject ?? new JsonObject();
    private bool AutoSync => Preferences.Bool("auto_sync");
    private void SavePreferences(JsonObject prefs) => LocalStore.Write(api.UserFile("preferences"), prefs);
    private void ApplyPreferences()
    {
        var prefs = Preferences; FontSize = prefs.Int("font_size", 14);
        Background = prefs.Text("theme") == "contrast" ? Brushes.White : new SolidColorBrush(Color.FromRgb(243, 246, 248));
        Foreground = prefs.Text("theme") == "contrast" ? Brushes.Black : new SolidColorBrush(Color.FromRgb(23, 52, 72));
    }
    private void UpdateIdentity()
    {
        var name = api.User.Text("Name");
        var shop = lookups["workshops"].Rows().FirstOrDefault(x => x.Int("id") == api.User.Int("WorkshopId")).Text("label", "Все цеха");
        HeaderIdentity.Text = $"◉ {name} · {api.User.Text("Role")} · {shop}";
    }
    private async void Toast(string message)
    {
        var revision = ++toastRevision; ToastText.Text = message; ToastBox.Visibility = Visibility.Visible;
        await Task.Delay(2500); if (revision == toastRevision) ToastBox.Visibility = Visibility.Collapsed;
    }
    private async void Shortcut(object sender, KeyEventArgs e)
    {
        if (!ready || locking || Application.Current.Windows.Count > 1) return;
        if (e.Key == Key.F5) { e.Handled = true; await LoadMetadata(); await LoadCurrent(); }
        else if (Keyboard.Modifiers == ModifierKeys.Control && e.Key == Key.F) { e.Handled = true; searchBox?.Focus(); searchBox?.SelectAll(); }
        else if (Keyboard.Modifiers == ModifierKeys.Control && e.Key == Key.N)
        {
            e.Handled = true; var resource = meta["resources"].Rows().FirstOrDefault(x => x.Text("key") == section);
            if (resource?.Bool("canWrite") == true) await Edit(resource, null);
        }
        else if (Keyboard.Modifiers == ModifierKeys.Control && e.Key == Key.L) { e.Handled = true; Lock(); }
    }
    private async Task RefreshNotifications()
    {
        var session = sessionRevision;
        try
        {
            var data = (await api.Get("/api/notifications")).Data;
            if (!ready || session != sessionRevision) return;
            notificationData = data;
            var read = LocalStore.Read(api.UserFile("notification-read")) as JsonObject ?? new JsonObject();
            NotificationsButton.Content = "● " + notificationData["items"].Rows().Count(x => !read.Bool(x.Text("id")));
        }
        catch (Exception e) { LocalStore.Log("NOTIFICATIONS", e.GetType().Name + ": " + e.Message); }
    }
    private async void Notifications_Click(object sender, RoutedEventArgs e)
    {
        await RefreshNotifications(); var window = DetailWindow("Уведомления", out var root); var body = new StackPanel(); root.Children.Add(new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto });
        var read = LocalStore.Read(api.UserFile("notification-read")) as JsonObject ?? new JsonObject();
        foreach (var item in notificationData["items"].Rows())
        {
            var box = new StackPanel(); box.Children.Add(Ui.Text(item.Text("title"), 16, true)); box.Children.Add(Ui.Text(item.Text("message"), 13));
            var actions = new WrapPanel(); box.Children.Add(actions);
            actions.Children.Add(Ui.Button(read.Bool(item.Text("id")) ? "Прочитано" : "Отметить прочитанным", (sender, _) => { read[item.Text("id")] = true; LocalStore.Write(api.UserFile("notification-read"), read); ((Button)sender).Content = "Прочитано"; NotificationsButton.Content = "● " + notificationData["items"].Rows().Count(x => !read.Bool(x.Text("id"))); }, true));
            if (item.Int("entity_id") > 0) actions.Children.Add(Ui.Button("Открыть", async (_, _) =>
            {
                read[item.Text("id")] = true; LocalStore.Write(api.UserFile("notification-read"), read); window.Close();
                var key = item.Text("resource");
                if (key is "equipment" or "work-orders" or "teams") await ShowDetails(key, item.Int("entity_id"));
                else { section = key; extraFilters.Clear(); search = ""; statusFilter = ""; page = 1; await LoadCurrent(); }
            }));
            body.Children.Add(Ui.Card(box));
        }
        if (body.Children.Count == 0) body.Children.Add(Ui.Text("Новых событий нет.")); window.ShowDialog(); await RefreshNotifications();
    }
    private async Task SyncQueue()
    {
        if (!ready || locking || syncing || !AutoSync || Application.Current.Windows.Count > 1 || api.Queue().Count == 0) return;
        syncing = true;
        try
        {
            var user = api.User.Int("Id"); var server = api.BaseUrl;
            foreach (var item in api.Queue())
            {
                if (!ready || api.User.Int("Id") != user || api.BaseUrl != server) break;
                await api.Mutate(item.Method, item.Path, item.Body, item.Id);
                if (!ready || api.User.Int("Id") != user || api.BaseUrl != server) break;
                api.RemoveQueued(item.Id);
            }
            QueueButton.Content = "Очередь: " + api.Queue().Count; Toast("Отложенные изменения отправлены"); await LoadCurrent();
        }
        catch (OfflineException) { /* Wait for next recovery probe; same request ID is retained. */ }
        catch (Exception e) { var prefs = Preferences; prefs["auto_sync"] = false; SavePreferences(prefs); Notify("Автоотправка остановлена. Запрос сохранён: " + e.Message); }
        finally { syncing = false; }
    }
    private void Settings_Click(object sender, RoutedEventArgs e)
    {
        var prefs = Preferences; var window = DetailWindow("Настройки рабочего места", out var root); var body = new StackPanel(); root.Children.Add(body);
        body.Children.Add(Ui.Text("Размер шрифта")); var size = new ComboBox { ItemsSource = new[] { 12, 14, 16, 18 }, SelectedItem = prefs.Int("font_size", 14), Width = 150, HorizontalAlignment = HorizontalAlignment.Left }; body.Children.Add(size);
        var contrast = new CheckBox { Content = "Контрастная светлая тема", IsChecked = prefs.Text("theme") == "contrast", Margin = new Thickness(0, 18, 0, 18) }; body.Children.Add(contrast);
        body.Children.Add(Ui.Text("Настройки таблиц: ширина колонок сохраняется после перетаскивания. Горячие клавиши: F5 — обновить; Ctrl+F — поиск; Ctrl+N — добавить; Ctrl+L — блокировка.", 14));
        body.Children.Add(Ui.Button("Применить и сохранить", async (_, _) => { prefs["font_size"] = (int)size.SelectedItem; prefs["theme"] = contrast.IsChecked == true ? "contrast" : "light"; SavePreferences(prefs); ApplyPreferences(); window.Close(); await LoadCurrent(); Toast("Настройки сохранены"); })); window.ShowDialog();
    }
    private void Queue_Click(object sender, RoutedEventArgs e)
    {
        var window = new Window { Owner = this, Title = "Очередь изменений", Width = 850, Height = 590, WindowStartupLocation = WindowStartupLocation.CenterOwner };
        Ui.Fit(window);
        var root = new DockPanel { Margin = new Thickness(22) }; window.Content = root;
        var top = new StackPanel(); top.Children.Add(Ui.Text("Отложенные изменения", 24, true)); top.Children.Add(Ui.Text("Повтор использует исходный Idempotency-Key и текущего пользователя. Конфликты остаются для ручного решения."));
        var auto = new CheckBox { Content = "Автоматически отправлять после восстановления связи", IsChecked = AutoSync, Margin = new Thickness(0, 10, 0, 12) }; auto.Click += (_, _) => { var prefs = Preferences; prefs["auto_sync"] = auto.IsChecked == true; SavePreferences(prefs); }; top.Children.Add(auto); DockPanel.SetDock(top, Dock.Top); root.Children.Add(top);
        var buttons = new WrapPanel { Margin = new Thickness(0, 12, 0, 0) }; DockPanel.SetDock(buttons, Dock.Bottom); root.Children.Add(buttons);
        var list = new ListBox { DisplayMemberPath = "Label", BorderBrush = Brushes.LightGray }; root.Children.Add(list);
        void Reload() { list.ItemsSource = api.Queue().Select(q => new QueueRow(q, $"{q.CreatedAt}   {q.Method} {q.Path}\n{q.Body?.ToJsonString() ?? "без тела"}")).ToList(); QueueButton.Content = $"Очередь: {api.Queue().Count}"; }
        var retry = new Button { Content = "Повторить выбранное" }; buttons.Children.Add(retry);
        retry.Click += async (_, _) =>
        {
            if (list.SelectedItem is not QueueRow row) return; retry.IsEnabled = false;
            try { await api.Mutate(row.Item.Method, row.Item.Path, row.Item.Body, row.Item.Id); api.RemoveQueued(row.Item.Id); Reload(); await LoadCurrent(); }
            catch (Exception ex) { MessageBox.Show(window, ex.Message + "\nЗапрос остался в очереди.", "Повтор не выполнен"); }
            finally { retry.IsEnabled = true; }
        };
        buttons.Children.Add(Ui.Button("Убрать из очереди", (_, _) =>
        {
            if (list.SelectedItem is QueueRow row && MessageBox.Show(window, "Убрать локальный запрос? Это не отменяет операцию, если сервер уже успел её выполнить.", "Подтверждение", MessageBoxButton.YesNo) == MessageBoxResult.Yes) { api.RemoveQueued(row.Item.Id); Reload(); }
        }, true)); Reload(); window.ShowDialog();
    }
    private record QueueRow(QueuedWrite Item, string Label);
}
