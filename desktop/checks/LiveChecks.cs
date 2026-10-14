using System.Net;
using System.Text.Json.Nodes;
using Toir.Desktop;

internal static class LiveChecks
{
    public static async Task Run()
    {
        var endpoint = Environment.GetEnvironmentVariable("TOIR_TEST_URL") ?? "http://127.0.0.1:8000";
        var password = Environment.GetEnvironmentVariable("TOIR_TEST_PASSWORD") ?? "ChampDemo2027!";
        int passed = 0;
        void Assert(bool condition, string name) { if (!condition) throw new InvalidOperationException("FAIL " + name); passed++; Console.WriteLine("PASS " + name); }
        using var admin = new ApiClient();
        await admin.Login(endpoint, "admin@toir.local", password);
        var meta = (await admin.Get("/api/meta")).Data;
        Assert(meta["resources"].Rows().Count() >= 10, "admin metadata exposes all resource forms");
        var lookups = (await admin.Get("/api/lookups")).Data;
        foreach (var resource in meta["resources"].Rows())
        {
            var key = resource.Text("key"); var records = (await admin.Get($"/api/{key}?search=&page=1&page_size=25&status=")).Data;
            Assert(records["items"] is JsonArray && records["total"] is not null, $"list envelope: {key}");
            foreach (var field in resource["fields"].Rows())
                if (field.Text("lookup") is { Length: > 0 } lookup && lookups[lookup] is not JsonArray) throw new Exception($"Missing lookup {lookup}");
        }
        var dashboard = (await admin.Get("/api/dashboard")).Data;
        Assert(dashboard["metrics"] is JsonObject && dashboard["recent_orders"] is JsonArray, "native dashboard contract");
        Assert((await admin.Get("/api/analytics")).Data["equipment_status"] is JsonArray, "native chart contract");
        Assert(dashboard["metrics"]?["today_orders"] is not null && dashboard["active_orders"] is JsonArray && dashboard["upcoming"] is JsonArray, "six KPI and active orders contract");
        var equipment = (await admin.Get("/api/equipment?page_size=1")).Data["items"].Rows().First();
        var details = (await admin.Get($"/api/equipment/{equipment.Int("Id")}/details")).Data;
        Assert(details["orders"] is JsonArray && details["schedule"] is JsonArray && details["history"] is JsonArray, "equipment linked details contract");
        var team = (await admin.Get("/api/teams?page_size=1")).Data["items"].Rows().First();
        var teamDetails = (await admin.Get($"/api/teams/{team.Int("Id")}")).Data;
        Assert(teamDetails["members"] is JsonArray && teamDetails["active_orders"] is JsonArray && teamDetails["workload"] is JsonObject, "team roster workload contract");
        Assert((await admin.Get("/api/notifications")).Data["items"] is JsonArray, "notifications contract");
        var sorted = (await admin.Get("/api/equipment?sort_by=Id&sort_dir=desc&page_size=50")).Data["items"].Rows().ToList();
        Assert(sorted.Select(x => x.Int("Id")).SequenceEqual(sorted.Select(x => x.Int("Id")).OrderDescending()), "server-side descending sort");
        Assert((await admin.Get("/api/schedule?date_from=2027-01-01&date_to=2027-01-31&page_size=100")).Data["items"].Rows().All(x => x.Text("PlannedAt").StartsWith("2027-01-")), "calendar date filter");
        foreach (var type in new[] { "equipment", "work-orders", "materials", "downtime", "schedule", "team-efficiency", "material-usage" })
        {
            var preview = (await admin.Get("/api/reports/preview?type=" + type + "&from=2026-01-01&to=2027-12-31")).Data;
            Assert(preview["rows"] is JsonArray && preview["columns"] is JsonArray && preview["summary"] is JsonObject, "report preview " + type);
        }
        var orders = (await admin.Get("/api/work-orders")).Data["items"].Rows().ToList();
        if (orders.Count > 0)
        {
            var order = (await admin.Get($"/api/work-orders/{orders[0].Int("Id")}")).Data;
            Assert(order["history"] is JsonArray && order["materials"] is JsonArray, "order details timeline materials contract");
            Assert((await admin.Get($"/api/work-orders/{orders[0].Int("Id")}/history")).Data is JsonArray, "order history contract");
            Assert((await admin.Get($"/api/work-orders/{orders[0].Int("Id")}/materials")).Data is JsonArray, "order materials contract");
        }
        foreach (var format in new[] { "pdf", "xlsx", "csv" })
        {
            var report = await admin.Mutate("POST", "/api/reports/export", new JsonObject { ["type"] = "equipment", ["format"] = format });
            var downloaded = await admin.Download(report.Text("url"), report.Text("filename"));
            Assert(File.Exists(downloaded) && new FileInfo(downloaded).Length > 50, "export download " + format);
        }
        var supplierId = 0;
        try
        {
            var payload = new JsonObject { ["Name"] = "DESKTOP-CHECK-" + Guid.NewGuid().ToString("N"), ["Phone"] = "000" }; var key = Guid.NewGuid().ToString();
            supplierId = (await admin.Mutate("POST", "/api/suppliers", payload, key)).Int("Id");
            Assert(supplierId > 0, "temporary supplier create via desktop client");
            Assert((await admin.Mutate("POST", "/api/suppliers", payload, key)).Int("Id") == supplierId, "real database idempotent create replay");
            Assert((await admin.Mutate("PUT", $"/api/suppliers/{supplierId}", new JsonObject { ["Phone"] = "001" })).Text("Phone") == "001", "temporary supplier update");
        }
        finally { if (supplierId > 0) { await admin.Mutate("DELETE", $"/api/suppliers/{supplierId}", null); Console.WriteLine("CLEANUP temporary supplier removed"); } }
        using var master = new ApiClient(); await master.Login(endpoint, "master@toir.local", password);
        var masterMeta = (await master.Get("/api/meta")).Data;
        Assert(masterMeta["resources"].Rows().All(r => r.Text("key") != "users"), "master navigation hides users");
        var masterEquipment = (await master.Get("/api/equipment")).Data["items"].Rows();
        Assert(masterEquipment.All(r => r.Int("WorkshopId") == master.User.Int("WorkshopId")), "master equipment scoped to own workshop");
        try { await master.Get("/api/users"); throw new Exception("Master accessed admin resource"); }
        catch (ApiException e) { Assert(e.Status == HttpStatusCode.Forbidden, "master forbidden admin request"); }
        await master.Logout();
        using var manager = new ApiClient(); await manager.Login(endpoint, "manager@toir.local", password);
        Assert((await manager.Get("/api/meta")).Data["resources"].Rows().All(r => !r.Bool("canWrite")), "manager native forms are read-only");
        await manager.Logout(); await admin.Logout();
        Console.WriteLine($"{passed} live API checks passed; no native UI was launched.");
    }
}
