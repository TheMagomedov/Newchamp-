using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;

namespace Toir.Desktop;

// Windows DPAPI CurrentUser. No password is persisted; ciphertext cannot be reused by another Windows user.
public static class SecureSession
{
    [StructLayout(LayoutKind.Sequential)] private struct Blob { public int Length; public IntPtr Data; }
    [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Unicode)] private static extern bool CryptProtectData(ref Blob input, string? description, IntPtr entropy, IntPtr reserved, IntPtr prompt, int flags, out Blob output);
    [DllImport("crypt32.dll", SetLastError = true)] private static extern bool CryptUnprotectData(ref Blob input, IntPtr description, IntPtr entropy, IntPtr reserved, IntPtr prompt, int flags, out Blob output);
    [DllImport("kernel32.dll")] private static extern IntPtr LocalFree(IntPtr value);
    private static byte[] Transform(byte[] value, bool protect)
    {
        var input = new Blob { Length = value.Length, Data = Marshal.AllocHGlobal(value.Length) }; Blob output = default;
        try
        {
            Marshal.Copy(value, 0, input.Data, value.Length);
            var ok = protect ? CryptProtectData(ref input, "ТОиР session", IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 1, out output) : CryptUnprotectData(ref input, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 1, out output);
            if (!ok) throw new Win32Exception(Marshal.GetLastWin32Error());
            var bytes = new byte[output.Length]; Marshal.Copy(output.Data, bytes, 0, bytes.Length); return bytes;
        }
        finally { for (int i = 0; i < input.Length; i++) Marshal.WriteByte(input.Data, i, 0); Marshal.FreeHGlobal(input.Data); if (output.Data != IntPtr.Zero) { for (int i = 0; i < output.Length; i++) Marshal.WriteByte(output.Data, i, 0); LocalFree(output.Data); } }
    }
    public static void Save(JsonNode session)
    {
        var bytes = Encoding.UTF8.GetBytes(session.ToJsonString());
        try { LocalStore.Write("session.dpapi.json", new JsonObject { ["ciphertext"] = Convert.ToBase64String(Transform(bytes, true)) }); }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }
    public static JsonNode? Read()
    {
        var text = LocalStore.Read("session.dpapi.json").Text("ciphertext"); if (text.Length == 0) return null;
        try { var bytes = Transform(Convert.FromBase64String(text), false); try { return JsonNode.Parse(bytes); } finally { CryptographicOperations.ZeroMemory(bytes); } }
        catch (Exception e) { LocalStore.Log("SESSION", e.GetType().Name); return null; }
    }
    public static void Clear() => LocalStore.Write("session.dpapi.json", new JsonObject());
}
