using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using System.Text.Json;
using Microsoft.Windows.Widgets;
using Microsoft.Windows.Widgets.Providers;

namespace Apex;

/// Windows 11 Widgets Board (and lock screen) provider. Each widget shows a picture of the real widget, the same page
/// the desktop widgets show (WidgetImages); when that can't be made, it falls back to a text card (Cards).
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
        public string LastData = "";   // what was last pushed
        public DateTimeOffset CheckedAt;
        public string? Image;          // picture of the real widget, as a data: URI (null: show the text card)
        public string ImageKey = "";   // size and settings it was taken with
        public string ImageData = "";  // text card data at the time, standing in for what it shows
        public DateTimeOffset ImageAt;
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
        ["apex.weekend"] = Kind.Weekend, ["apex.circuit"] = Kind.Circuit,
    };
    static readonly Dictionary<Kind, string> Names = new()
    {
        [Kind.Race] = "APEX race mode", [Kind.Next] = "Next session", [Kind.Countdown] = "Countdown", [Kind.Timing] = "Live timing",
        [Kind.Driver] = "Driver", [Kind.Favourite] = "Favourite driver", [Kind.Wdc] = "Drivers' championship",
        [Kind.Wcc] = "Constructors' championship", [Kind.Weekend] = "Race weekend", [Kind.Circuit] = "Circuit",
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

    /// Every second. Widgets on the open board are checked each tick; the rest (closed board, lock screen, which may
    /// never be "active") every 5 minutes, or every minute during a session. Fetches: 30 s while live, 5 min otherwise.
    static async Task Tick()
    {
        var now = DateTimeOffset.Now;
        var live = Snapshots.Values.Any(l => l is not null && RaceMode.Of(l.Snapshot, now) == Mode.Live);
        var idle = live ? TimeSpan.FromMinutes(1) : TimeSpan.FromMinutes(5);
        List<Live> due = [.. Widgets.Values.Where(w => !w.Customizing && (w.Active || now - w.CheckedAt >= idle))];
        if (due.Count == 0 || !await Gate.WaitAsync(0)) return;
        try
        {
            if (now - lastFetch > (live ? TimeSpan.FromSeconds(30) : TimeSpan.FromMinutes(5)))
            {
                foreach (var driver in due.Select(w => w.Settings.Driver).Distinct()) Snapshots[driver ?? ""] = await Api.Snapshot(driver);
                lastFetch = DateTimeOffset.Now;
            }
            foreach (var w in due) { w.CheckedAt = now; await Render(w, force: false); }
        }
        finally { Gate.Release(); }
    }

    static async Task Push(string id, bool force)
    {
        if (!Widgets.TryGetValue(id, out var w) || w.Customizing) return;
        await Gate.WaitAsync();
        try
        {
            if (!Snapshots.ContainsKey(w.Settings.Driver ?? ""))
                Snapshots[w.Settings.Driver ?? ""] = Api.Cached(w.Settings.Driver) ?? await Api.Snapshot(w.Settings.Driver);
            await Render(w, force);
        }
        finally { Gate.Release(); }
    }

    static async Task Render(Live w, bool force)
    {
        Snapshots.TryGetValue(w.Settings.Driver ?? "", out var loaded);
        var now = DateTimeOffset.Now;
        var (template, data) = Cards.Build(w.Kind, w.Size, loaded, w.Settings, now);

        // Retake the picture when what the widget shows changed (the text card's data stands in for that), at most once
        // a minute, or every 20 s during a session, so a ticking countdown doesn't retake it every second. A new size or
        // new settings retake it straight away. A failed attempt waits the same interval before trying again. Every 15
        // minutes regardless, for changes the text doesn't carry (a silhouette that was missing, a new style).
        var key = $"{w.Size}|{JsonSerializer.Serialize(w.Settings)}";
        var live = loaded is not null && RaceMode.Of(loaded.Snapshot, now) == Mode.Live;
        if (loaded is not null && (key != w.ImageKey ||
            data != w.ImageData && now - w.ImageAt >= (live ? TimeSpan.FromSeconds(20) : TimeSpan.FromMinutes(1)) ||
            now - w.ImageAt >= TimeSpan.FromMinutes(15)))
        {
            w.Image = await WidgetImages.Render(w.Kind, w.Size, w.Settings);
            (w.ImageKey, w.ImageData, w.ImageAt) = (key, data, now);
        }
        if (loaded is not null && w.Image is not null)
            (template, data) = ("image", JsonSerializer.Serialize(new { image = w.Image, alt = Names[w.Kind] }));

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
        try { return SharedFile.Read(FilePath) is { } json ? JsonSerializer.Deserialize<WidgetSettings>(json) ?? new() : new(); }
        catch { return new(); }
    }
    public static void Save(WidgetSettings s) => SharedFile.Write(FilePath, JsonSerializer.Serialize(s));
}
