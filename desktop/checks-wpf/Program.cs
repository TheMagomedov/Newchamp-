using System.IO;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Toir.Desktop;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        Environment.SetEnvironmentVariable("TOIR_DESKTOP_DATA", Path.Combine(Path.GetTempPath(), "ToirVisualChecks", Guid.NewGuid().ToString("N")));
        using var api = new ApiClient();
        api.Login(Environment.GetEnvironmentVariable("TOIR_TEST_URL") ?? "http://127.0.0.1:8000", "admin@toir.local", "ChampDemo2027!").GetAwaiter().GetResult();
        var meta = api.Get("/api/meta").GetAwaiter().GetResult().Data;
        var lookups = api.Get("/api/lookups").GetAwaiter().GetResult().Data;
        var dashboard = api.Get("/api/dashboard").GetAwaiter().GetResult().Data;
        var report = api.Get("/api/reports/preview?type=downtime&from=2026-01-01&to=2027-12-31").GetAwaiter().GetResult().Data;
        var records = meta["resources"].Rows().ToDictionary(r => r.Text("key"), r => api.Get("/api/" + r.Text("key")).GetAwaiter().GetResult().Data);
        api.Logout().GetAwaiter().GetResult();
        var app = new App(); app.InitializeComponent();
        SessionSafetyChecks.Run();
        var window = new MainWindow();
        Set(window, "meta", meta); Set(window, "lookups", lookups);
        Call(window, "BuildNavigation");
        ((TextBlock)window.FindName("IdentityText")).Text = "Администратор\nadmin";
        ((TextBlock)window.FindName("HeaderIdentity")).Text = "◉ Администратор · admin · Все цеха";
        ((TextBlock)window.FindName("StatusText")).Text = "Подключено • проверка макета 1366×768";
        Call(window, "RenderDashboard", dashboard);
        Directory.CreateDirectory("checks-wpf/artifacts");
        Render(window, "checks-wpf/artifacts/dashboard.png", 1366, 730);
        var equipment = meta["resources"].Rows().First(r => r.Text("key") == "equipment");
        Set(window, "section", "equipment"); ((TextBlock)window.FindName("PageTitle")).Text = "Оборудование";
        ((TextBlock)window.FindName("Breadcrumb")).Text = "ТОиР / Оборудование";
        Call(window, "RenderResource", equipment, records["equipment"]);
        ResourceUiChecks.Run(window);
        Render(window, "checks-wpf/artifacts/equipment.png", 1366, 730);
        Set(window, "section", "schedule"); ((TextBlock)window.FindName("PageTitle")).Text = "График ТО";
        var schedule = records["schedule"]["items"].Rows().ToList();
        if (schedule.Count > 0)
        {
            var month = schedule.Where(r => DateTime.TryParse(r.Text("PlannedAt"), out _)).GroupBy(r => DateTime.Parse(r.Text("PlannedAt")).ToString("yyyy-MM")).OrderByDescending(g => g.Count()).First();
            Set(window, "calendarMonth", DateTime.Parse(month.Key + "-01")); schedule = month.ToList();
        }
        ((TextBlock)window.FindName("Breadcrumb")).Text = "ТОиР / График ТО";
        Call(window, "RenderSchedule", schedule); Render(window, "checks-wpf/artifacts/schedule.png", 1366, 730);
        Set(window, "section", "reports"); ((TextBlock)window.FindName("PageTitle")).Text = "Отчёты и экспорт";
        ((TextBlock)window.FindName("Breadcrumb")).Text = "ТОиР / Отчёты и экспорт";
        Call(window, "RenderReportWorkspace"); Render(window, "checks-wpf/artifacts/reports.png", 1366, 730);
        var reportBody = new StackPanel(); Call(window, "RenderReportPreview", reportBody, report);
        var reportWindow = new Window { Content = new ScrollViewer { Content = reportBody }, Background = Brushes.White, FontFamily = window.FontFamily, FontSize = 14, Foreground = window.Foreground };
        Render(reportWindow, "checks-wpf/artifacts/report-preview.png", 1100, 700); reportWindow.Close();
        var loginWindow = new LoginDialog(api, false); Render(loginWindow, "checks-wpf/artifacts/login.png", 470, 690); loginWindow.Close();
        int forms = 0;
        foreach (var resource in meta["resources"].Rows())
        {
            var record = records[resource.Text("key")]["items"].Rows().FirstOrDefault(); if (record is null) continue;
            var editor = new EditorDialog(resource.Text("label"), resource["fields"].Rows(), lookups, record);
            var payload = Call(editor, "Read") as JsonObject;
            if (payload is null) throw new Exception("Invalid form payload " + resource.Text("key"));
            Console.WriteLine("PASS native form serialization: " + resource.Text("key")); forms++;
            if (resource.Text("key") == "equipment") Render(editor, "checks-wpf/artifacts/equipment-form.png", 550, 610);
            editor.Close();
        }
        Console.WriteLine($"{forms} native forms checked; 7 off-screen PNG renders saved. No window shown.");
        window.Close(); app.Shutdown();
    }
    private static void Set(object target, string name, object value) => target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(target, value);
    private static object? Call(object target, string name, params object[] args)
    {
        try { return target.GetType().GetMethod(name, BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(target, args); }
        catch (TargetInvocationException e) { throw e.InnerException ?? e; }
    }
    private static void Render(Window window, string path, int width, int height)
    {
        var content = (FrameworkElement)window.Content; window.Content = null;
        var background = new Border { Background = window.Background, Child = content, Width = width, Height = height };
        System.Windows.Documents.TextElement.SetFontFamily(background, window.FontFamily);
        System.Windows.Documents.TextElement.SetFontSize(background, window.FontSize);
        System.Windows.Documents.TextElement.SetForeground(background, window.Foreground);
        background.Measure(new Size(width, height)); background.Arrange(new Rect(0, 0, width, height)); background.UpdateLayout();
        var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32); bitmap.Render(background);
        var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap)); using var file = File.Create(path); encoder.Save(file);
        background.Child = null; window.Content = content;
    }
}
