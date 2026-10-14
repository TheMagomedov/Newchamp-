using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json.Nodes;
using Toir.Desktop;

// Headless contract checks: does not open WPF windows or contact the real API/database.
var scratch = Path.Combine(Path.GetTempPath(), "ToirDesktopChecks", Guid.NewGuid().ToString("N"));
Environment.SetEnvironmentVariable("TOIR_DESKTOP_DATA", scratch);
if (args.Contains("--live")) { await LiveChecks.Run(); return; }
var listener = new HttpListener();
var portProbe = new TcpListener(IPAddress.Loopback, 0); portProbe.Start();
var port = ((IPEndPoint)portProbe.LocalEndpoint).Port; portProbe.Stop();
var baseUrl = $"http://127.0.0.1:{port}"; listener.Prefixes.Add(baseUrl + "/"); listener.Start();
int checks = 0, writes = 0, refreshes = 0; bool expireOnce = true;
var requestKeys = new HashSet<string>();
void Assert(bool condition, string label) { if (!condition) throw new Exception("FAIL " + label); Console.WriteLine("PASS " + label); checks++; }
var staleOrder = JsonNode.Parse("""{"Id":42,"TeamId":1,"ActualStart":"2027-02-01T09:00:00Z","ActualEnd":null,"CompletionReport":"Старый отчёт"}""")!;
var unchangedTransition = JsonNode.Parse("""{"status":"ожидает материалов","team_id":1,"actual_start":"2027-02-01T09:00:00","actual_end":null,"completion_report":"Старый отчёт"}""")!.AsObject();
var partial = TransitionPayload.Build(unchangedTransition, staleOrder);
Assert(partial.Count == 1 && partial["status"]?.ToString() == "ожидает материалов", "status-only transition omits stale brigade dates and report");
var assignment = unchangedTransition.DeepClone().AsObject(); assignment["status"] = "назначена";
Assert(TransitionPayload.Build(assignment, staleOrder)["team_id"]?.GetValue<int>() == 1, "explicit assignment preserves chosen brigade");
var editedTransition = unchangedTransition.DeepClone().AsObject(); editedTransition["team_id"] = 2; editedTransition["completion_report"] = "Новый отчёт";
var editedPayload = TransitionPayload.Build(editedTransition, staleOrder);
Assert(editedPayload["team_id"]?.GetValue<int>() == 2 && editedPayload["completion_report"]?.ToString() == "Новый отчёт" && !editedPayload.ContainsKey("actual_start"), "transition includes deliberate edits but not unchanged timestamps");
JsonObject Envelope(JsonNode? data) => new() { ["success"] = true, ["data"] = data, ["message"] = "ok", ["error_code"] = null };
JsonObject Tokens(int id, string email) => new() { ["access_token"] = "test-access", ["refresh_token"] = "test-refresh", ["user"] = new JsonObject { ["Id"] = id, ["Email"] = email, ["Name"] = "Test", ["Role"] = "admin" } };
var server = Task.Run(async () =>
{
    while (listener.IsListening)
    {
        HttpListenerContext context;
        try { context = await listener.GetContextAsync(); } catch (HttpListenerException) { break; } catch (ObjectDisposedException) { break; }
        var path = context.Request.Url!.AbsolutePath;
        var bodyText = await new StreamReader(context.Request.InputStream).ReadToEndAsync();
        var body = string.IsNullOrEmpty(bodyText) ? new JsonObject() : JsonNode.Parse(bodyText)!;
        JsonNode response = new JsonObject();
        if (path == "/api/auth/login") response = Envelope(Tokens(body.Text("email") == "two@test" ? 2 : 1, body.Text("email")));
        else if (path == "/api/auth/refresh") { refreshes++; response = Envelope(Tokens(1, "one@test")); }
        else if (path == "/api/refresh-check" && expireOnce) { expireOnce = false; context.Response.StatusCode = 401; response = new JsonObject { ["success"] = false, ["message"] = "expired" }; }
        else if (path == "/api/denied") { context.Response.StatusCode = 403; response = new JsonObject { ["success"] = false, ["message"] = "Недостаточно прав", ["error_code"] = "FORBIDDEN" }; }
        else if (context.Request.HttpMethod == "POST")
        {
            if (requestKeys.Add(context.Request.Headers["Idempotency-Key"] ?? "")) writes++;
            response = Envelope(new JsonObject { ["Id"] = writes });
        }
        else response = Envelope(new JsonObject { ["items"] = new JsonArray(new JsonObject { ["Id"] = 1, ["Name"] = "Станок" }), ["total"] = 1 });
        var bytes = Encoding.UTF8.GetBytes(response.ToJsonString()); context.Response.ContentType = "application/json"; context.Response.ContentLength64 = bytes.Length;
        await context.Response.OutputStream.WriteAsync(bytes); context.Response.Close();
    }
});
using var api = new ApiClient();
await api.Login(baseUrl, "one@test", "sample-password");
Assert(api.User.Int("Id") == 1, "login envelope and user");
var fresh = await api.Get("/api/equipment");
Assert(!fresh.Offline && fresh.Data.Int("total") == 1, "online GET and persistent cache");
await api.Get("/api/refresh-check");
Assert(refreshes == 1, "401 refresh and exactly one retry");
try { await api.Get("/api/denied"); throw new Exception("Expected rejection"); }
catch (ApiException ex) { Assert(ex.Status == HttpStatusCode.Forbidden && ex.Message == "Недостаточно прав", "403 never replaced by cache"); }
var key = Guid.NewGuid().ToString(); var payload = new JsonObject { ["Name"] = "Новый станок" };
api.Enqueue(new(key, "POST", "/api/equipment", payload, DateTime.Now.ToString("g")));
api.Enqueue(new(key, "POST", "/api/equipment", payload, DateTime.Now.ToString("g")));
Assert(api.Queue().Count == 1, "local queue deduplicates request IDs");
await api.Mutate("POST", "/api/equipment", payload, key); await api.Mutate("POST", "/api/equipment", payload, key);
Assert(writes == 1, "manual replay preserves idempotency key");
await api.Login(baseUrl, "two@test", "sample-password");
Assert(api.Queue().Count == 0, "queue is scoped by authenticated user");
await api.Login(baseUrl, "one@test", "sample-password"); api.RemoveQueued(key);
Assert(api.Queue().Count == 0, "successful request removed from queue");
api.RememberSession(true);
Assert(!File.ReadAllText(Path.Combine(scratch, "session.dpapi.json")).Contains("test-refresh"), "remember-me refresh token is DPAPI ciphertext");
using (var restored = new ApiClient())
{
    Assert(await restored.TryRestore() && restored.User.Int("Id") == 1, "remember-me restores identity through server refresh");
    restored.RememberSession(false);
}
Assert(SecureSession.Read()?.Text("refresh_token", "") is null or "", "remember-me opt-out clears stored token");
listener.Stop(); await server;
var cached = await api.Get("/api/equipment"); Assert(cached.Offline && cached.Data.Int("total") == 1, "offline GET returns labelled last successful snapshot");
await api.Login(baseUrl, "one@test", "sample-password", 1); Assert(api.User.Int("Id") == 1, "offline unlock of existing session");
try { await api.Login(baseUrl, "one@test", "wrong-password", 1); throw new Exception("Expected rejection"); }
catch (InvalidOperationException) { Assert(true, "offline unlock rejects wrong password"); }
Assert(!Directory.EnumerateFiles(scratch).Any(f => File.ReadAllText(f).Contains("sample-password") || File.ReadAllText(f).Contains("test-access") || File.ReadAllText(f).Contains("test-refresh")), "credentials and tokens not persisted");
Console.WriteLine($"{checks} checks passed. Temporary isolated data: {scratch}");
