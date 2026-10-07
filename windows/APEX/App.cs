using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.XamlTypeInfo;

namespace Apex;

/// The APEX app (spec §17): settings and the widget gallery. The screen itself is app.html from the data server, in a
/// WebView2 (same F1 look and live previews as the widgets); this class is the bridge that owns the settings files.
public sealed class App : Application, IXamlMetadataProvider
{
    // With no XAML pages, nothing generates the type-info provider WinUI's control styles need
    // (otherwise: "Cannot find a resource with the given key: AcrylicBackgroundFillColorDefaultBrush").
    readonly XamlControlsXamlMetaDataProvider controlsMetadata = new();
    public IXamlType GetXamlType(Type type) => controlsMetadata.GetXamlType(type);
    public IXamlType GetXamlType(string fullName) => controlsMetadata.GetXamlType(fullName);
    public XmlnsDefinition[] GetXmlnsDefinitions() => controlsMetadata.GetXmlnsDefinitions();

    static readonly Windows.UI.Color Carbon = Windows.UI.Color.FromArgb(255, 0x0E, 0x0E, 0x14);
    Window? window;
    // Created in OnLaunched, not as a field: a XAML control built during App construction initializes WinUI before
    // our metadata provider is in place, and XamlControlsResources then fails ("AcrylicBackgroundFillColorDefaultBrush").
    WebView2 web = null!;

    public App()
    {
        // WinUI crashes surface only as 0xc000027b in the event log; keep the real message.
        Directory.CreateDirectory(DesktopConfig.Dir);
        UnhandledException += (_, e) => File.AppendAllText(Path.Combine(DesktopConfig.Dir, "crash.log"), $"{DateTimeOffset.Now:u} {e.Exception}\n");
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        Resources.MergedDictionaries.Add(new XamlControlsResources());
        web = new WebView2 { DefaultBackgroundColor = Carbon };
        window = new Window { Title = "APEX", Content = web };
        var bar = window.AppWindow.TitleBar;  // carbon title bar, so the window reads as one piece
        bar.BackgroundColor = bar.InactiveBackgroundColor = bar.ButtonBackgroundColor = bar.ButtonInactiveBackgroundColor = Carbon;
        bar.ForegroundColor = bar.ButtonForegroundColor = Microsoft.UI.Colors.White;
        bar.ButtonHoverBackgroundColor = Windows.UI.Color.FromArgb(255, 0x22, 0x22, 0x2C);
        var area = Microsoft.UI.Windowing.DisplayArea.Primary.WorkArea;
        window.AppWindow.Resize(new Windows.Graphics.SizeInt32(Math.Min(1280, area.Width * 9 / 10), Math.Min(1000, area.Height * 9 / 10)));
        window.Activate();
        _ = InitAsync();
    }

    async Task InitAsync()
    {
        await web.EnsureCoreWebView2Async();
        web.CoreWebView2.Settings.AreDevToolsEnabled = false;
        web.CoreWebView2.Settings.IsStatusBarEnabled = false;
        web.CoreWebView2.WebMessageReceived += (_, e) => OnMessage(e.WebMessageAsJson);
        // The data server may still be starting (just after logon): retry until the page loads.
        web.CoreWebView2.NavigationCompleted += async (_, e) =>
        {
            if (e.IsSuccess) return;
            web.NavigateToString("<body style='background:#0E0E14;color:#fff;font:600 16px Segoe UI;display:grid;place-items:center;height:90vh'>Starting the APEX data server…</body>");
            await Task.Delay(4000);
            web.Source = new Uri($"{Api.BaseUrl}/app.html");
        };
        web.Source = new Uri($"{Api.BaseUrl}/app.html");
    }

    /// Commands from app.html. Every reply carries the full state, so the page never drifts from the files.
    void OnMessage(string json)
    {
        string? done = null, error = null;
        try
        {
            var m = JsonNode.Parse(json)!;
            var d = Defaults.Load();
            switch ((string?)m["cmd"])
            {
                case "setDriver":
                    Defaults.Save(d with { Driver = (string?)m["id"] });
                    done = "Driver updated";
                    break;
                case "setDensity" when (string?)m["value"] is "minimal" or "standard" or "detailed":
                    Defaults.Save(d with { Density = (string)m["value"]! });
                    break;
                case "addDesktop" when (string?)m["size"] is "s" or "m" or "l":
                    DesktopConfig.Add((string)m["kind"]!, (string)m["size"]!);
                    DesktopConfig.EnsureHostRunning();
                    done = "Added to your desktop";
                    break;
                case "removeDesktop":
                    DesktopConfig.Remove((string)m["id"]!);
                    done = "Removed from your desktop";
                    break;
                case "openLockScreen":
                    _ = Windows.System.Launcher.LaunchUriAsync(new Uri("ms-settings:lockscreen"));
                    break;
            }
        }
        catch (Exception e)  // a busy file, a malformed message: say so on screen, never close the app
        {
            error = e is IOException ? "Couldn't save just now. Try again." : "Something went wrong. Try again.";
            File.AppendAllText(Path.Combine(DesktopConfig.Dir, "crash.log"), $"{DateTimeOffset.Now:u} (handled) {e}\n");
        }
        SendState(done, error);
    }

    void SendState(string? done = null, string? error = null)
    {
        var d = Defaults.Load();
        List<DesktopWidget> desktop;
        try { desktop = DesktopConfig.Load() ?? []; } catch (IOException) { desktop = []; }
        web.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(new
        {
            type = "state", driver = d.Driver, density = d.Density, done, error,
            desktop = desktop.Select(w => new { id = w.Id, kind = w.Kind, size = w.Size }),
        }));
    }
}
