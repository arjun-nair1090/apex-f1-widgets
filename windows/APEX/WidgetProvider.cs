using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using System.Text.Json;
using Microsoft.Windows.Widgets;
using Microsoft.Windows.Widgets.Providers;

namespace Apex;

/// Windows 11 Widgets Board provider. The board hosts our Adaptive Cards; we push (template, data) per widget.
[ComVisible(true)]
[Guid("8C4D7A1E-4F0B-4E2A-9B7C-5A3E2D1F0A6B")]  // must match Package.appxmanifest CreateInstance ClassId
public sealed partial class WidgetProvider : IWidgetProvider, IWidgetProvider2
{
    sealed class Live
    {
        public required string Id;
        public required Kind Kind;
        public string Size = "medium";
        public WidgetSettings Settings = new();
        public bool Active;            // visible on the open board
        public bool Customizing;
        public string LastData = "";
    }

    // COM calls and the ticker run on different threads.
    static readonly ConcurrentDictionary<string, Live> Widgets = new();
    static readonly ConcurrentDictionary<string, Loaded?> Snapshots = new();  // by driver
    static readonly SemaphoreSlim Gate = new(1, 1);
    static Timer? ticker;
    static DateTimeOffset lastFetch = DateTimeOffset.MinValue;
    public static readonly ManualResetEventSlim Empty = new(false);

    static readonly Dictionary<string, Kind> Definitions = new()
    {
        ["apex.racemode"] = Kind.Race, ["apex.next"] = Kind.Next, ["apex.countdown"] = Kind.Countdown, ["apex.timing"] = Kind.Timing,
        ["apex.driver"] = Kind.Driver, ["apex.favourite"] = Kind.Favourite, ["apex.wdc"] = Kind.Wdc, ["apex.wcc"] = Kind.Wcc,
        ["apex.weekend"] = Kind.Weekend,
    };

    public WidgetProvider()
    {
        // The board may restart us with widgets already pinned: recover them and their settings.
        foreach (var info in WidgetManager.GetDefault().GetWidgetInfos() ?? [])
        {
            var ctx = info.WidgetContext;
            if (!Definitions.TryGetValue(ctx.DefinitionId, out var kind)) continue;
            Widgets[ctx.Id] = new Live { Id = ctx.Id, Kind = kind, Size = SizeName(ctx.Size), Settings = Parse(info.CustomState), Active = ctx.IsActive };
        }
        ticker ??= new Timer(_ => _ = Tick(), null, TimeSpan.Zero, TimeSpan.FromSeconds(1));
    }

    public void CreateWidget(WidgetContext ctx)
    {
        if (!Definitions.TryGetValue(ctx.DefinitionId, out var kind)) return;
        Widgets[ctx.Id] = new Live { Id = ctx.Id, Kind = kind, Size = SizeName(ctx.Size), Settings = Defaults.Load(), Active = ctx.IsActive };
        Empty.Reset();
        _ = Push(ctx.Id, force: true);
    }

    public void DeleteWidget(string widgetId, string customState)
    {
        Widgets.TryRemove(widgetId, out _);
        if (Widgets.IsEmpty) Empty.Set();
    }

    public void OnActionInvoked(WidgetActionInvokedArgs args)
    {
        var id = args.WidgetContext.Id;
        if (!Widgets.TryGetValue(id, out var w)) return;
        switch (args.Verb)
        {
            case "refresh":
                lastFetch = DateTimeOffset.MinValue;
                break;
            case "save":
                var input = JsonDocument.Parse(args.Data).RootElement;
                var driver = input.TryGetProperty("driver", out var d) ? d.GetString() : null;
                var density = input.TryGetProperty("density", out var dn) ? dn.GetString() ?? "standard" : "standard";
                w.Settings = new WidgetSettings(string.IsNullOrEmpty(driver) || driver == "none" ? null : driver, density);
                w.Customizing = false;
                lastFetch = DateTimeOffset.MinValue;
                break;
            case "cancel":
                w.Customizing = false;
                break;
        }
        _ = Push(id, force: true);
    }

    public void OnWidgetContextChanged(WidgetContextChangedArgs args)
    {
        if (!Widgets.TryGetValue(args.WidgetContext.Id, out var w)) return;
        w.Size = SizeName(args.WidgetContext.Size);  // new size, new layout (spec §27)
        _ = Push(w.Id, force: true);
    }

    public void Activate(WidgetContext ctx)
    {
        if (Widgets.TryGetValue(ctx.Id, out var w)) { w.Active = true; _ = Push(ctx.Id, force: true); }
    }

    public void Deactivate(string widgetId)
    {
        if (Widgets.TryGetValue(widgetId, out var w)) w.Active = false;
    }

    public void OnCustomizationRequested(WidgetCustomizationRequestedArgs args)
    {
        if (!Widgets.TryGetValue(args.WidgetContext.Id, out var w)) return;
        w.Customizing = true;
        _ = ShowCustomization(w);
    }

    // ---------- rendering ----------

    /// Every second while the board is open; pushes only when the rendered data changed (so standings never re-push,
    /// countdowns push once a second). Fetches: 30 s while live, 5 min otherwise. Hidden widgets cost nothing.
    static async Task Tick()
    {
        List<Live> visible;
        visible = [.. Widgets.Values.Where(w => w.Active && !w.Customizing)];
        if (visible.Count == 0 || !await Gate.WaitAsync(0)) return;
        try
        {
            var live = Snapshots.Values.Any(l => l is not null && RaceMode.Of(l.Snapshot, DateTimeOffset.Now) == Mode.Live);
            if (DateTimeOffset.Now - lastFetch > (live ? TimeSpan.FromSeconds(30) : TimeSpan.FromMinutes(5)))
            {
                foreach (var driver in visible.Select(w => w.Settings.Driver).Distinct()) Snapshots[driver ?? ""] = await Api.Snapshot(driver);
                lastFetch = DateTimeOffset.Now;
            }
            foreach (var w in visible) Render(w, force: false);
        }
        finally { Gate.Release(); }
    }

    static async Task Push(string id, bool force)
    {
        if (!Widgets.TryGetValue(id, out var w) || w.Customizing) return;
        if (!Snapshots.ContainsKey(w.Settings.Driver ?? ""))
            Snapshots[w.Settings.Driver ?? ""] = Api.Cached(w.Settings.Driver) ?? await Api.Snapshot(w.Settings.Driver);
        Render(w, force);
    }

    static void Render(Live w, bool force)
    {
        Snapshots.TryGetValue(w.Settings.Driver ?? "", out var loaded);
        var (template, data) = Cards.Build(w.Kind, w.Size, loaded, w.Settings, DateTimeOffset.Now);
        if (!force && data == w.LastData) return;
        w.LastData = data;
        WidgetManager.GetDefault().UpdateWidget(new WidgetUpdateRequestOptions(w.Id)
        {
            Template = Cards.Template(template),
            Data = data,
            CustomState = JsonSerializer.Serialize(w.Settings),
        });
    }

    static async Task ShowCustomization(Live w)
    {
        var drivers = await Api.Drivers();
        var data = JsonSerializer.Serialize(new
        {
            driver = w.Settings.Driver ?? "none", density = w.Settings.Density,
            drivers = new[] { new { title = "None", value = "none" } }
                .Concat(drivers.Select(d => new { title = $"{d.FirstName} {d.LastName}", value = d.Id })),
        });
        WidgetManager.GetDefault().UpdateWidget(new WidgetUpdateRequestOptions(w.Id) { Template = Cards.Template("customize"), Data = data });
    }

    static string SizeName(WidgetSize s) => s switch { WidgetSize.Small => "small", WidgetSize.Large => "large", _ => "medium" };

    static WidgetSettings Parse(string? state)
    {
        try { return string.IsNullOrEmpty(state) ? Defaults.Load() : JsonSerializer.Deserialize<WidgetSettings>(state) ?? new(); }
        catch { return new(); }
    }
}

/// Defaults for newly added widgets, set in the companion window.
public static class Defaults
{
    static readonly string FilePath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "APEX", "defaults.json");
    public static WidgetSettings Load()
    {
        try { return JsonSerializer.Deserialize<WidgetSettings>(File.ReadAllText(FilePath)) ?? new(); } catch { return new(); }
    }
    public static void Save(WidgetSettings s)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
        File.WriteAllText(FilePath, JsonSerializer.Serialize(s));
    }
}
