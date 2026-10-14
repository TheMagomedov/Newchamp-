namespace Toir.Desktop;

// Учебный модуль: запуск окна, сеанс входа и навигация между разделами.
public partial class MainWindow : Window
{
    private readonly ApiClient api = new();
    private JsonNode meta = new JsonObject(), lookups = new JsonObject();
    private string section = "dashboard", search = "", statusFilter = "";
    private int page = 1, loadRevision, sessionRevision;
    private DateTime lastInput = DateTime.UtcNow;
    private bool locking, ready, closed;
    private readonly DispatcherTimer idle = new() { Interval = TimeSpan.FromSeconds(1) };
    private readonly DispatcherTimer refresh = new() { Interval = TimeSpan.FromSeconds(60) };

    public MainWindow()
    {
        InitializeComponent();
        Ui.Fit(this);
        Loaded += async (_, _) =>
        {
            var restored = await api.TryRestore(); if (closed) return;
            if (!restored && new LoginDialog(api, false) { Owner = this }.ShowDialog() != true) { Close(); return; }
            await StartSession();
        };
        InputManager.Current.PreProcessInput += CaptureInput;
        idle.Tick += (_, _) => { if (ready && !locking && DateTime.UtcNow - lastInput >= TimeSpan.FromSeconds(15)) Lock(); };
        refresh.Tick += async (_, _) => { if (ready && !locking && Application.Current.Windows.Count == 1) { if (section == "dashboard") await LoadCurrent(); await RefreshNotifications(); } };
        sync.Tick += async (_, _) => await SyncQueue();
        PreviewKeyDown += Shortcut;
        Closed += (_, _) => { closed = true; StopSession(); InputManager.Current.PreProcessInput -= CaptureInput; api.Dispose(); };
    }
    private async Task StartSession()
    {
        if (closed) return;
        var session = ++sessionRevision;
        ready = true; lastInput = DateTime.UtcNow;
        section = "dashboard"; page = 1; search = ""; statusFilter = ""; extraFilters.Clear(); sortBy = "Id"; sortDir = "asc";
        IdentityText.Text = $"{api.User.Text("Name")}\n{api.User.Text("Role")}";
        await LoadMetadata(); if (!ready || session != sessionRevision) return;
        ApplyPreferences(); BuildNavigation(); await LoadCurrent();
        if (!ready || session != sessionRevision) return;
        await RefreshNotifications();
        if (ready && session == sessionRevision) { idle.Start(); refresh.Start(); sync.Start(); }
    }
    private void StopSession()
    {
        ready = false; sessionRevision++; loadRevision++; toastRevision++;
        idle.Stop(); refresh.Stop(); sync.Stop();
        meta = new JsonObject(); lookups = new JsonObject(); notificationData = new JsonObject();
        ContentHost.Children.Clear(); NavPanel.Children.Clear(); IdentityText.Text = HeaderIdentity.Text = "";
        NotificationsButton.Content = "● 0"; QueueButton.Content = "Очередь: 0";
        BusyBar.Visibility = ToastBox.Visibility = Visibility.Collapsed; Notify(null);
    }
    private void CaptureInput(object sender, PreProcessInputEventArgs e)
    {
        if (e.StagingItem.Input is MouseEventArgs or KeyboardEventArgs or TouchEventArgs or StylusEventArgs) lastInput = DateTime.UtcNow;
    }
    private void Lock()
    {
        if (!ready || locking) return; locking = true;
        var owner = Application.Current.Windows.OfType<Window>().LastOrDefault(w => w.IsActive) ?? this;
        try { new LoginDialog(api, true) { Owner = owner }.ShowDialog(); }
        finally { locking = false; lastInput = DateTime.UtcNow; }
    }
    private void Lock_Click(object sender, RoutedEventArgs e) => Lock();
    private async void Logout_Click(object sender, RoutedEventArgs e)
    {
        if (!ready) return; StopSession(); await api.Logout();
        if (closed) return;
        if (new LoginDialog(api, false) { Owner = this }.ShowDialog() != true) { Close(); return; }
        await StartSession();
    }
    private async void Refresh_Click(object sender, RoutedEventArgs e) { if (ready && !locking) { await LoadMetadata(); await LoadCurrent(); } }
    private async Task LoadMetadata()
    {
        var session = sessionRevision;
        try
        {
            var nextMeta = (await api.Get("/api/meta")).Data;
            if (!ready || session != sessionRevision) return;
            var nextLookups = (await api.Get("/api/lookups")).Data;
            if (ready && session == sessionRevision) { meta = nextMeta; lookups = nextLookups; }
        }
        catch (Exception e) { if (ready && session == sessionRevision) Notify(e.Message); }
    }
    private void BuildNavigation()
    {
        NavPanel.Children.Clear();
        AddNav("dashboard", "Обзор");
        foreach (var resource in meta["resources"].Rows()) AddNav(resource.Text("key"), resource.Text("label"));
        AddNav("reports", "Отчёты и экспорт");
        AddNav("analytics", "Аналитика");
    }
    private void AddNav(string key, string label)
    {
        var button = Ui.Button(label, async (_, _) => { section = key; page = 1; search = ""; statusFilter = ""; extraFilters.Clear(); sortBy = "Id"; await LoadCurrent(); });
        button.Tag = key; button.HorizontalContentAlignment = HorizontalAlignment.Left; button.Margin = new Thickness(0, 0, 0, 5);
        button.Background = Brushes.Transparent; button.Foreground = new SolidColorBrush(Color.FromRgb(205, 224, 233));
        NavPanel.Children.Add(button);
    }
    private void Notify(string? message)
    {
        NoticeText.Text = message ?? ""; NoticeBox.Visibility = string.IsNullOrWhiteSpace(message) ? Visibility.Collapsed : Visibility.Visible;
    }
    private void ReadState(ReadResult result)
    {
        if (result.Offline) Notify($"Нет подключения. Показана сохранённая копия от {result.CachedAt}. Изменения можно добавить в очередь; автоотправка включается отдельно в её настройках.");
        StatusText.Text = result.Offline ? "Офлайн • данные могут быть устаревшими" : $"Подключено • {api.BaseUrl} • обновлено {DateTime.Now:HH:mm:ss}";
        QueueButton.Content = $"Очередь: {api.Queue().Count}";
    }
    private async Task LoadCurrent()
    {
        if (!ready) return;
        var revision = ++loadRevision;
        Notify(null); StatusText.Text = "Загрузка…"; BusyBar.Visibility = Visibility.Visible;
        foreach (var button in NavPanel.Children.OfType<Button>()) button.Background = Equals(button.Tag, section) ? new SolidColorBrush(Color.FromRgb(8, 127, 130)) : Brushes.Transparent;
        try
        {
            if (section is "dashboard" or "analytics")
            {
                PageTitle.Text = section == "dashboard" ? "Панель управления" : "Аналитика";
                var result = await api.Get("/api/" + section); if (revision != loadRevision) return;
                ReadState(result); RenderDashboard(result.Data);
            }
            else if (section == "reports") { PageTitle.Text = "Отчёты и экспорт"; RenderReportWorkspace(); StatusText.Text = "Выберите отчёт и период"; }
            else if (section == "schedule") { PageTitle.Text = "График ТО"; await LoadSchedule(revision); }
            else
            {
                var resource = meta["resources"].Rows().FirstOrDefault(r => r.Text("key") == section);
                if (resource is null) return; PageTitle.Text = resource.Text("label");
                var result = await api.Get($"/api/{section}?search={Uri.EscapeDataString(search)}&page={page}&page_size={pageSize}&status={Uri.EscapeDataString(statusFilter)}&sort_by={sortBy}&sort_dir={sortDir}" + FilterQuery());
                if (revision != loadRevision) return; ReadState(result); RenderResource(resource, result.Data);
            }
        }
        catch (Exception e)
        {
            if (revision != loadRevision || !ready) return;
            Notify(e.Message); StatusText.Text = "Действие не выполнено"; LocalStore.Log("UI", e.GetType().Name + ": " + e.Message);
            if (e is ApiException { Status: System.Net.HttpStatusCode.Unauthorized }) Lock();
        }
        finally { if (revision == loadRevision && ready) { BusyBar.Visibility = Visibility.Collapsed; Breadcrumb.Text = "ТОиР / " + PageTitle.Text; UpdateIdentity(); } }
    }
}
