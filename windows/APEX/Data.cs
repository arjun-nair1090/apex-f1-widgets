using System.Reflection;
using System.Text.Json;

namespace Apex;

// Mirrors backend/apex/schemas.py. Deserialized with snake_case naming.

public record Session(string Id, int Round, string Type, string Label, DateTimeOffset StartsAt, DateTimeOffset EndsAt, string State);
public record Race(int Season, int Round, string Name, string ShortName, string CircuitName, string? CountryCode, int? LapsTotal, List<Session> Sessions);
public record DriverStanding(int Position, string DriverId, string Code, string Name, string? TeamId, string? TeamColor, double Points, int Wins);
public record ConstructorStanding(int Position, string TeamId, string Name, string ShortName, string? Color, double Points, int Wins);
public record WeekendResult(string SessionType, int? Position, string? Gap);
public record DriverDetail(string Id, string Code, string FirstName, string LastName, string? CountryCode, string? TeamId, string? TeamName,
    string? TeamColor, int? Position, double Points, int Wins, int Podiums, int Poles, List<int?> Last5, List<WeekendResult> Weekend,
    int? RaceNumber = null);
public record DriverSummary(string Id, string Code, string FirstName, string LastName, string? TeamName);
public record TimingRow(int Position, int DriverNumber, string Code, string? TeamColor, string? Time, string? Gap, string? Interval,
    List<string?>? Sectors, bool InPit, bool? Drs);
public record Timing(string SessionId, string SessionType, string? Phase, int? Lap, int? LapsTotal, bool Final, DateTimeOffset UpdatedAt, List<TimingRow> Rows)
{
    public bool IsRace => SessionType is "RACE" or "SPRINT";
}
public record WidgetSnapshot(DateTimeOffset GeneratedAt, string Mode, Race? Race, Session? NextSession, Timing? Live, Timing? Results,
    List<DriverStanding> Drivers, List<ConstructorStanding> Constructors, DriverDetail? Driver, bool LiveUnavailable);

/// Silhouette: the favourite driver's team-colour silhouette as a data: URI (cards can't fetch from localhost).
public record Loaded(WidgetSnapshot Snapshot, DateTimeOffset? StaleSince, string? Silhouette = null);

/// One request per refresh; last good snapshot per driver on disk so a widget is never empty (spec §23).
public static class Api
{
    static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower, PropertyNameCaseInsensitive = true };
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(10) };
    public static readonly string BaseUrl = Environment.GetEnvironmentVariable("APEX_BASE_URL")
        ?? typeof(Api).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>().FirstOrDefault(a => a.Key == "ApexBaseUrl")?.Value
        ?? "http://localhost:8077";
    static readonly string CacheDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "APEX");

    static string CachePath(string? driver) => Path.Combine(CacheDir, $"snapshot-{driver ?? "none"}.json");

    public static async Task<Loaded?> Snapshot(string? driver)
    {
        try
        {
            var url = $"{BaseUrl}/api/widgets/snapshot" + (driver is null ? "" : $"?driver={Uri.EscapeDataString(driver)}");
            var text = await Http.GetStringAsync(url);
            var snap = JsonSerializer.Deserialize<WidgetSnapshot>(text, Json)!;
            Directory.CreateDirectory(CacheDir);
            await File.WriteAllTextAsync(CachePath(driver), text);
            return new Loaded(snap, null, await Silhouette(snap.Driver?.Id));
        }
        catch (Exception) when (Cached(driver) is { } cached)
        {
            return cached;
        }
        catch (Exception)
        {
            return null;
        }
    }

    /// 206 px PNG from /api/drivers/{id}/silhouette.png, cached on disk so cards keep it offline.
    static async Task<string?> Silhouette(string? driverId)
    {
        if (driverId is null) return null;
        var file = Path.Combine(CacheDir, $"silhouette-{driverId}.png");
        try
        {
            var png = await Http.GetByteArrayAsync($"{BaseUrl}/api/drivers/{Uri.EscapeDataString(driverId)}/silhouette.png?size=206");
            await File.WriteAllBytesAsync(file, png);
        }
        catch (Exception) when (File.Exists(file)) { }  // offline: last good one
        catch (Exception) { return null; }               // no portrait for this driver
        return "data:image/png;base64," + Convert.ToBase64String(await File.ReadAllBytesAsync(file));
    }

    public static Loaded? Cached(string? driver)
    {
        try
        {
            var snap = JsonSerializer.Deserialize<WidgetSnapshot>(File.ReadAllText(CachePath(driver)), Json)!;
            var png = Path.Combine(CacheDir, $"silhouette-{snap.Driver?.Id}.png");
            return new Loaded(snap, snap.GeneratedAt,
                File.Exists(png) ? "data:image/png;base64," + Convert.ToBase64String(File.ReadAllBytes(png)) : null);
        }
        catch { return null; }
    }

    public static async Task<List<DriverSummary>> Drivers()
    {
        try { return JsonSerializer.Deserialize<List<DriverSummary>>(await Http.GetStringAsync($"{BaseUrl}/api/drivers"), Json) ?? []; }
        catch { return []; }
    }
}

/// Settings files are shared by three processes (APEX app, desktop host, widget provider). Write to a temp file and
/// swap it in; retry briefly on sharing violations. A reader and a writer can then never crash each other.
public static class SharedFile
{
    public static string? Read(string path)
    {
        for (int attempt = 0; ; attempt++)
        {
            try { return File.ReadAllText(path); }
            catch (Exception e) when (e is FileNotFoundException or DirectoryNotFoundException) { return null; }
            catch (IOException) when (attempt < 20) { Thread.Sleep(25); }
        }
    }

    public static void Write(string path, string text)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var tmp = $"{path}.{Environment.ProcessId}.tmp";
        File.WriteAllText(tmp, text);
        for (int attempt = 0; ; attempt++)
        {
            try { File.Move(tmp, path, overwrite: true); return; }
            catch (IOException) when (attempt < 20) { Thread.Sleep(25); }
        }
    }
}

public enum Mode { Live, Results, Countdown, Next }

/// Mirror of backend/apex/racemode.py, evaluated at render time so cards flip at boundaries without a fetch.
public static class RaceMode
{
    static readonly TimeSpan Soon = TimeSpan.FromMinutes(15), ResultsWindow = TimeSpan.FromMinutes(90);
    public static readonly TimeSpan CountdownWindow = TimeSpan.FromHours(3);

    public static string State(Session s, DateTimeOffset now) =>
        now >= s.EndsAt ? "finished" : now >= s.StartsAt ? "live" : now >= s.StartsAt - Soon ? "starting_soon" : "upcoming";

    public static (Mode, Session?) Of(List<Session> sessions, DateTimeOffset now)
    {
        var o = sessions.OrderBy(s => s.StartsAt).ToList();
        if (o.FirstOrDefault(s => s.StartsAt <= now && now < s.EndsAt) is { } live) return (Mode.Live, live);
        if (o.LastOrDefault(s => s.EndsAt <= now) is { } ended && now - ended.EndsAt < ResultsWindow) return (Mode.Results, ended);
        var up = o.FirstOrDefault(s => s.StartsAt > now);
        return up is null ? (Mode.Next, null) : (up.StartsAt - now <= CountdownWindow ? Mode.Countdown : Mode.Next, up);
    }

    public static Mode Of(WidgetSnapshot s, DateTimeOffset now)
    {
        if (s.Race is null) return Mode.Next;
        var (m, _) = Of(s.Race.Sessions, now);
        if (m != Mode.Results || s.Results is not null) return m;
        var up = s.Race.Sessions.Where(x => x.StartsAt > now).OrderBy(x => x.StartsAt).FirstOrDefault();
        return up is not null && up.StartsAt - now <= CountdownWindow ? Mode.Countdown : Mode.Next;
    }

    public static Session? NextSession(WidgetSnapshot s, DateTimeOffset now) =>
        s.Race?.Sessions.OrderBy(x => x.StartsAt).FirstOrDefault(x => x.EndsAt > now) ?? s.NextSession;
}

public static class Fmt
{
    public static string Day(DateTimeOffset d) => d.ToLocalTime().ToString("ddd", System.Globalization.CultureInfo.InvariantCulture).ToUpperInvariant();
    public static string HhMm(DateTimeOffset d) => d.ToLocalTime().ToString("HH:mm");
    public static string DayTime(DateTimeOffset d) => $"{Day(d)} · {HhMm(d)}";
    public static string Points(double p) => p % 1 == 0 ? ((int)p).ToString() : p.ToString("0.0");
    public static string Pad(int n) => n.ToString("00");
    public static string Short(string type) => type switch { "QUALIFYING" => "QUALI", "SPRINT_QUALIFYING" => "SPRINT QUALI", _ => type };
    public static string Ago(DateTimeOffset since, DateTimeOffset now)
    {
        var s = (int)(now - since).TotalSeconds;
        return s < 60 ? $"{s}S" : s < 3600 ? $"{s / 60}M" : $"{s / 3600}H";
    }
    /// "2D 03:11" past a day, "HH:MM:SS" inside one.
    public static string Countdown(DateTimeOffset target, DateTimeOffset now)
    {
        var t = target - now;
        if (t < TimeSpan.Zero) t = TimeSpan.Zero;
        return t.Days > 0 ? $"{t.Days}D {t.Hours:00}:{t.Minutes:00}" : $"{t.Hours:00}:{t.Minutes:00}:{t.Seconds:00}";
    }
}
