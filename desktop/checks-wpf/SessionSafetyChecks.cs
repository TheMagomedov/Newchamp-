using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using Toir.Desktop;

internal static class SessionSafetyChecks
{
    private const BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;
    private static int passed;

    public static void Run()
    {
        var previousContext = SynchronizationContext.Current;
        var previousShutdown = Application.Current.ShutdownMode;
        Application.Current.ShutdownMode = ShutdownMode.OnExplicitShutdown;
        SynchronizationContext.SetSynchronizationContext(new CheckContext());
        try
        {
            CheckStopSession();
            CheckStaleMetadata();
            CheckStaleLoad(HttpStatusCode.OK);
            CheckStaleLoad(HttpStatusCode.InternalServerError);
            Console.WriteLine($"{passed} off-screen session safety assertions passed; no HTTP/DB writes or visible windows.");
        }
        finally { SynchronizationContext.SetSynchronizationContext(previousContext); Application.Current.ShutdownMode = previousShutdown; }
    }

    private static void CheckStopSession()
    {
        var window = new MainWindow();
        try
        {
            Set(window, "ready", true); Set(window, "sessionRevision", 2); Set(window, "loadRevision", 8);
            Set(window, "meta", JsonNode.Parse("""{"resources":[{"key":"users"}]}""")!);
            Set(window, "lookups", JsonNode.Parse("""{"masters":[{"id":1}]}""")!);
            Set(window, "notificationData", JsonNode.Parse("""{"items":[{"id":"old"}]}""")!);
            Element<TextBlock>(window, "IdentityText").Text = "Previous user";
            Element<TextBlock>(window, "HeaderIdentity").Text = "Previous account";
            Element<Grid>(window, "ContentHost").Children.Add(new TextBlock { Text = "Private data" });
            Element<StackPanel>(window, "NavPanel").Children.Add(new Button { Content = "Users" });
            Element<ProgressBar>(window, "BusyBar").Visibility = Visibility.Visible;
            Element<Border>(window, "ToastBox").Visibility = Visibility.Visible;
            foreach (var name in new[] { "idle", "refresh", "sync" }) Get<DispatcherTimer>(window, name).Start();
            Call(window, "StopSession");
            Assert(!Get<bool>(window, "ready"), "session is disabled before logout awaits");
            Assert(Get<int>(window, "sessionRevision") == 3 && Get<int>(window, "loadRevision") == 9, "pending work invalidated");
            Assert(new[] { "meta", "lookups", "notificationData" }.All(name => Get<JsonObject>(window, name).Count == 0), "old account metadata cleared");
            Assert(Element<Grid>(window, "ContentHost").Children.Count == 0 && Element<StackPanel>(window, "NavPanel").Children.Count == 0, "old account content and navigation cleared");
            Assert(Element<TextBlock>(window, "IdentityText").Text == "" && Element<TextBlock>(window, "HeaderIdentity").Text == "", "old identity cleared");
            Assert(Element<ProgressBar>(window, "BusyBar").Visibility == Visibility.Collapsed && Element<Border>(window, "ToastBox").Visibility == Visibility.Collapsed, "pending busy/toast state cleared");
            Assert(new[] { "idle", "refresh", "sync" }.All(name => !Get<DispatcherTimer>(window, name).IsEnabled), "all session timers stopped");
        }
        finally { window.Close(); }
    }

    private static void CheckStaleMetadata()
    {
        var window = new MainWindow(); using var handler = AttachHandler(window);
        try
        {
            Set(window, "ready", true);
            var task = (Task)Call(window, "LoadMetadata")!;
            Call(window, "StopSession");
            handler.Complete(HttpStatusCode.OK, """{"resources":[{"key":"users"}]}""");
            Await(task);
            Assert(handler.Requests == 1, "stale metadata does not request another account's lookups");
            Assert(Get<JsonObject>(window, "meta").Count == 0, "stale metadata is not assigned after logout");
        }
        finally { window.Close(); }
    }

    private static void CheckStaleLoad(HttpStatusCode status)
    {
        var window = new MainWindow(); using var handler = AttachHandler(window);
        try
        {
            Set(window, "ready", true);
            var task = (Task)Call(window, "LoadCurrent")!;
            Call(window, "StopSession");
            Element<TextBlock>(window, "Breadcrumb").Text = "New page";
            Element<TextBlock>(window, "HeaderIdentity").Text = "New account";
            Element<TextBlock>(window, "StatusText").Text = "New status";
            var replacement = new TextBlock { Text = "New content" };
            Element<Grid>(window, "ContentHost").Children.Add(replacement);
            handler.Complete(status, "{}"); Await(task);
            Assert(Element<Grid>(window, "ContentHost").Children[0] == replacement, $"{status}: stale response cannot redraw content");
            Assert(Element<Border>(window, "NoticeBox").Visibility == Visibility.Collapsed, $"{status}: stale error cannot show a notification");
            Assert(Element<TextBlock>(window, "Breadcrumb").Text == "New page" && Element<TextBlock>(window, "HeaderIdentity").Text == "New account", $"{status}: stale finally cannot redraw breadcrumb/identity");
            Assert(Element<TextBlock>(window, "StatusText").Text == "New status", $"{status}: stale request cannot replace current status");
        }
        finally { window.Close(); }
    }

    private static DelayedHandler AttachHandler(MainWindow window)
    {
        var api = Get<ApiClient>(window, "api");
        Get<HttpClient>(api, "http").Dispose();
        var handler = new DelayedHandler(); Set(api, "http", new HttpClient(handler)); return handler;
    }
    private sealed class DelayedHandler : HttpMessageHandler
    {
        private readonly TaskCompletionSource<HttpResponseMessage> response = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public int Requests { get; private set; }
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Requests++;
            return Requests == 1 ? response.Task : Task.FromResult(MakeResponse(HttpStatusCode.OK, "{}"));
        }
        public void Complete(HttpStatusCode status, string body) => response.SetResult(MakeResponse(status, body));
        private static HttpResponseMessage MakeResponse(HttpStatusCode status, string body) => new(status) { Content = new StringContent(body, Encoding.UTF8, "application/json") };
    }
    private static void Await(Task task)
    {
        var timer = Stopwatch.StartNew();
        var context = (CheckContext)SynchronizationContext.Current!;
        while (!task.IsCompleted && timer.Elapsed < TimeSpan.FromSeconds(5)) context.Step();
        if (!task.IsCompleted) throw new TimeoutException("Session check did not complete in five seconds.");
        task.GetAwaiter().GetResult();
    }
    // Pump only test continuations, never WPF StartupUri/Loaded events or login dialogs.
    private sealed class CheckContext : SynchronizationContext
    {
        private readonly ConcurrentQueue<Action> callbacks = new();
        public override void Post(SendOrPostCallback callback, object? state) => callbacks.Enqueue(() => callback(state));
        public void Step() { if (callbacks.TryDequeue(out var callback)) callback(); else Thread.Sleep(1); }
    }
    private static T Element<T>(MainWindow window, string name) where T : FrameworkElement => (T)window.FindName(name);
    private static T Get<T>(object target, string name) => (T)target.GetType().GetField(name, Private)!.GetValue(target)!;
    private static void Set(object target, string name, object value) => target.GetType().GetField(name, Private)!.SetValue(target, value);
    private static object? Call(object target, string name) => target.GetType().GetMethod(name, Private)!.Invoke(target, null);
    private static void Assert(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException("FAIL " + message);
        passed++; Console.WriteLine("PASS " + message);
    }
}
