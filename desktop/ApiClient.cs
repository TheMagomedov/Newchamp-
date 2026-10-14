using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Toir.Desktop;

public static class JsonExt
{
    public static string Text(this JsonNode? node, string key, string fallback = "") => node?[key]?.ToString() ?? fallback;
    public static int Int(this JsonNode? node, string key, int fallback = 0) => int.TryParse(node.Text(key), out var n) ? n : fallback;
    public static bool Bool(this JsonNode? node, string key, bool fallback = false) => bool.TryParse(node.Text(key), out var value) ? value : fallback;
    public static IEnumerable<JsonNode> Rows(this JsonNode? node) => node is JsonArray a ? a.OfType<JsonNode>() : [];
}

public static class LocalStore
{
    public static readonly string Root = Environment.GetEnvironmentVariable("TOIR_DESKTOP_DATA") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Toir.Desktop");
    static LocalStore() => Directory.CreateDirectory(Root);
    public static void Log(string kind, string details)
    {
        try { File.AppendAllText(Path.Combine(Root, $"desktop-{DateTime.Today:yyyy-MM-dd}.log"), $"{DateTime.Now:O} [{kind}] {details}{Environment.NewLine}"); } catch (IOException) { }
    }
    public static string Hash(string text) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text)));
    public static JsonNode? Read(string file)
    {
        try { return JsonNode.Parse(File.ReadAllText(Path.Combine(Root, file))); } catch (Exception e) when (e is IOException or JsonException) { return null; }
    }
    public static void Write(string file, JsonNode node)
    {
        var target = Path.Combine(Root, file);
        File.WriteAllText(target + ".tmp", node.ToJsonString());
        File.Move(target + ".tmp", target, true);
    }
}

public sealed class ApiException(string message, HttpStatusCode status, string code = "") : Exception(message)
{
    public HttpStatusCode Status { get; } = status;
    public string Code { get; } = code;
}
public sealed class OfflineException(string message, Exception inner) : Exception(message, inner);
public record ReadResult(JsonNode Data, bool Offline, string? CachedAt = null);
public record QueuedWrite(string Id, string Method, string Path, JsonNode? Body, string CreatedAt);

public sealed class ApiClient : IDisposable
{
    private readonly HttpClient http = new() { Timeout = TimeSpan.FromSeconds(15) };
    private string accessToken = "", refreshToken = "";
    private readonly byte[] unlockSalt = RandomNumberGenerator.GetBytes(32);
    private byte[]? unlockHash;
    public string BaseUrl { get; private set; } = "http://127.0.0.1:8000";
    public JsonNode? User { get; private set; }
    public string Email => User.Text("Email");
    public bool CanWrite => User.Text("Role").ToLowerInvariant() is not ("viewer" or "observer" or "наблюдатель");
    private string Scope => LocalStore.Hash(BaseUrl + "|" + User.Int("Id"));
    private string QueueFile => "queue-" + Scope + ".json";
    public string UserFile(string name) => name + "-" + Scope + ".json";
    public bool Remember { get; private set; }
    public void RememberSession(bool enabled)
    {
        Remember = enabled;
        if (enabled) SaveSession(); else SecureSession.Clear();
    }
    private void SaveSession()
    {
        if (Remember && User is not null) SecureSession.Save(new JsonObject { ["url"] = BaseUrl, ["refresh_token"] = refreshToken, ["user_id"] = User.Int("Id") });
    }
    public async Task<bool> TryRestore()
    {
        var saved = SecureSession.Read(); if (saved is null || saved.Text("refresh_token").Length == 0) return false;
        try
        {
            BaseUrl = saved.Text("url");
            var tokens = await Send("POST", "/api/auth/refresh", new JsonObject { ["refresh_token"] = saved.Text("refresh_token") }, authenticated: false, allowRefresh: false);
            if (tokens["user"].Int("Id") != saved.Int("user_id")) throw new InvalidOperationException("Сохранённый сеанс не совпадает с пользователем.");
            accessToken = tokens.Text("access_token"); refreshToken = tokens.Text("refresh_token"); User = tokens["user"]?.DeepClone(); Remember = true; SaveSession(); return true;
        }
        catch (OfflineException) { return false; }
        catch (Exception e) { LocalStore.Log("SESSION", e.GetType().Name); SecureSession.Clear(); return false; }
    }

    public async Task Login(string baseUrl, string email, string password, int? expectedId = null)
    {
        if (!Uri.TryCreate(baseUrl.TrimEnd('/'), UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https"))
            throw new ArgumentException("Введите адрес API, например http://127.0.0.1:8000.");
        var oldUrl = BaseUrl;
        BaseUrl = baseUrl.TrimEnd('/');
        try
        {
            var data = await Send("POST", "/api/auth/login", new JsonObject { ["email"] = email, ["password"] = password }, authenticated: false);
            if (expectedId is not null && data["user"].Int("Id") != expectedId)
                throw new InvalidOperationException("Разблокировать сеанс может только тот же пользователь.");
            accessToken = data.Text("access_token"); refreshToken = data.Text("refresh_token"); User = data["user"]?.DeepClone();
            unlockHash = Rfc2898DeriveBytes.Pbkdf2(password, unlockSalt, 100_000, HashAlgorithmName.SHA256, 32);
            LocalStore.Write("settings.json", new JsonObject { ["url"] = BaseUrl, ["email"] = email });
            LocalStore.Log("LOGIN", $"User {User.Int("Id")}");
            SaveSession();
        }
        catch (OfflineException) when (expectedId is not null && User.Int("Id") == expectedId && email == Email && unlockHash is not null)
        {
            BaseUrl = oldUrl;
            var candidate = Rfc2898DeriveBytes.Pbkdf2(password, unlockSalt, 100_000, HashAlgorithmName.SHA256, 32);
            if (!CryptographicOperations.FixedTimeEquals(candidate, unlockHash)) throw new InvalidOperationException("Неверный пароль текущего локального сеанса.");
            LocalStore.Log("UNLOCK", "Offline session unlock; credentials held in memory only");
        }
        catch { BaseUrl = oldUrl; throw; }
    }

    public async Task<ReadResult> Get(string path)
    {
        var file = "cache-" + LocalStore.Hash(Scope + path) + ".json";
        try
        {
            var data = await Send("GET", path);
            try { LocalStore.Write(file, new JsonObject { ["at"] = DateTime.Now.ToString("g"), ["data"] = data.DeepClone() }); }
            catch (IOException e) { LocalStore.Log("CACHE", e.Message); }
            return new(data, false);
        }
        catch (OfflineException)
        {
            var cached = LocalStore.Read(file);
            if (cached?["data"] is null) throw;
            return new(cached["data"]!.DeepClone(), true, cached.Text("at"));
        }
    }

    public Task<JsonNode> Mutate(string method, string path, JsonNode? body, string? requestId = null) => Send(method, path, body, requestId ?? Guid.NewGuid().ToString());

    private async Task<JsonNode> Send(string method, string path, JsonNode? body = null, string? requestId = null, bool authenticated = true, bool allowRefresh = true)
    {
        using var request = new HttpRequestMessage(new HttpMethod(method), BaseUrl + path);
        if (authenticated) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
        if (requestId is not null) request.Headers.Add("Idempotency-Key", requestId);
        if (body is not null) request.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
        try
        {
            using var response = await http.SendAsync(request);
            var raw = await response.Content.ReadAsStringAsync();
            if (response.StatusCode == HttpStatusCode.Unauthorized && authenticated && allowRefresh && refreshToken.Length > 0)
            {
                var tokens = await Send("POST", "/api/auth/refresh", new JsonObject { ["refresh_token"] = refreshToken }, authenticated: false, allowRefresh: false);
                accessToken = tokens.Text("access_token"); refreshToken = tokens.Text("refresh_token", refreshToken);
                SaveSession();
                return await Send(method, path, body, requestId, authenticated, false);
            }
            JsonNode? envelope = null;
            try { if (raw.Length > 0) envelope = JsonNode.Parse(raw); } catch (JsonException) { }
            if (!response.IsSuccessStatusCode || envelope?.Bool("success", true) == false)
            {
                var message = envelope.Text("message", envelope.Text("detail", $"Ошибка сервера {(int)response.StatusCode}."));
                LocalStore.Log("API", $"{method} {path}: {(int)response.StatusCode} {envelope.Text("error_code")} {message}");
                throw new ApiException(message, response.StatusCode, envelope.Text("error_code"));
            }
            return envelope?["data"]?.DeepClone() ?? envelope ?? new JsonObject();
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException)
        {
            LocalStore.Log("OFFLINE", $"{method} {path}: {e.GetType().Name}");
            throw new OfflineException("Сервер недоступен или не ответил за 15 секунд. Проверьте подключение и состояние API.", e);
        }
    }

    public List<QueuedWrite> Queue() => LocalStore.Read(QueueFile)?.Deserialize<List<QueuedWrite>>() ?? [];
    public void Enqueue(QueuedWrite item)
    {
        var queue = Queue();
        if (queue.All(x => x.Id != item.Id)) queue.Add(item);
        LocalStore.Write(QueueFile, JsonSerializer.SerializeToNode(queue)!);
    }
    public void RemoveQueued(string id) => LocalStore.Write(QueueFile, JsonSerializer.SerializeToNode(Queue().Where(x => x.Id != id))!);

    public async Task Logout()
    {
        try { await Send("POST", "/api/auth/logout", new JsonObject { ["refresh_token"] = refreshToken }); }
        catch (Exception e) { LocalStore.Log("LOGOUT", e.GetType().Name); }
        finally { Remember = false; SecureSession.Clear(); accessToken = ""; refreshToken = ""; User = null; if (unlockHash is not null) CryptographicOperations.ZeroMemory(unlockHash); unlockHash = null; }
    }

    public async Task<string> Download(string url, string fileName)
    {
        var uri = Uri.TryCreate(url, UriKind.Absolute, out var absolute) ? absolute : new Uri(BaseUrl + "/" + url.TrimStart('/'));
        if (uri.Scheme is not ("http" or "https") || uri.Authority != new Uri(BaseUrl).Authority)
            throw new InvalidOperationException("Ссылка экспорта должна вести на текущий сервер API.");
        using var request = new HttpRequestMessage(HttpMethod.Get, uri);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
        using var response = await http.SendAsync(request);
        response.EnsureSuccessStatusCode();
        var dir = Path.Combine(LocalStore.Root, "Exports"); Directory.CreateDirectory(dir);
        var path = Path.Combine(dir, Path.GetFileName(fileName));
        await File.WriteAllBytesAsync(path, await response.Content.ReadAsByteArrayAsync());
        return path;
    }
    public void Dispose() => http.Dispose();
}
