using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.XamlTypeInfo;

namespace Apex;

/// Companion window (spec §17). Widgets are customized natively on the board (Customize menu); this sets defaults for new
/// widgets and shows data health. Built in code (no XAML pages) and themed by the system, so it feels native.
public sealed class App : Application, IXamlMetadataProvider
{
    Window? window;

    // With no XAML pages, nothing generates the type-info provider WinUI's control styles need
    // (otherwise: "Cannot find a resource with the given key: AcrylicBackgroundFillColorDefaultBrush").
    readonly XamlControlsXamlMetaDataProvider controlsMetadata = new();
    public IXamlType GetXamlType(Type type) => controlsMetadata.GetXamlType(type);
    public IXamlType GetXamlType(string fullName) => controlsMetadata.GetXamlType(fullName);
    public XmlnsDefinition[] GetXmlnsDefinitions() => controlsMetadata.GetXmlnsDefinitions();

    public App()
    {
        // WinUI crashes surface only as 0xc000027b in the event log; keep the real message.
        UnhandledException += (_, e) => File.AppendAllText(
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "APEX", "crash.log"),
            $"{DateTimeOffset.Now:u} {e.Exception}\n");
        Directory.CreateDirectory(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "APEX"));
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        Resources.MergedDictionaries.Add(new XamlControlsResources());
        window = new Window { Title = "APEX", SystemBackdrop = new MicaBackdrop(), ExtendsContentIntoTitleBar = true };
        window.AppWindow.Resize(new Windows.Graphics.SizeInt32(560, 720));
        window.Content = Build();
        window.Activate();
    }

    UIElement Build()
    {
        var defaults = Defaults.Load();
        var status = new TextBlock { Text = "Checking…", Opacity = 0.7 };
        var driver = new ComboBox { Header = "Favourite driver", PlaceholderText = "Loading drivers…", MinWidth = 320 };
        var density = new RadioButtons { Header = "Information", MaxColumns = 3 };
        foreach (var d in new[] { "Minimal", "Standard", "Detailed" }) density.Items.Add(d);
        density.SelectedIndex = defaults.Density switch { "minimal" => 0, "detailed" => 2, _ => 1 };

        List<DriverSummary> drivers = [];
        bool loading = false;  // rebuilding the list fires SelectionChanged: those aren't the user's choices
        void Save()
        {
            if (loading) return;
            Defaults.Save(new WidgetSettings(
                driver.SelectedIndex > 0 ? drivers[driver.SelectedIndex - 1].Id : null,
                new[] { "minimal", "standard", "detailed" }[Math.Clamp(density.SelectedIndex, 0, 2)]));
        }
        driver.SelectionChanged += (_, _) => Save();
        density.SelectionChanged += (_, _) => Save();

        async void Refresh()
        {
            var current = Defaults.Load().Driver;
            var list = await Api.Drivers();
            loading = true;
            if (list.Count > 0)  // offline: keep what's shown rather than collapsing to "None"
            {
                drivers = list;
                driver.Items.Clear();
                driver.Items.Add("None");
                foreach (var d in drivers) driver.Items.Add($"{d.FirstName} {d.LastName}");
                driver.SelectedIndex = Math.Max(0, drivers.FindIndex(d => d.Id == current) + 1);
            }
            loading = false;
            var snap = await Api.Snapshot(current);
            status.Text = snap switch
            {
                null => "Can't reach the APEX service. Widgets keep showing the last data they received.",
                { StaleSince: { } since } => $"Offline. Showing data from {Fmt.Ago(since, DateTimeOffset.Now).ToLowerInvariant()} ago.",
                { Snapshot: var s } => s.LiveUnavailable ? "Schedule and standings: OK · Live timing: unavailable" : "Schedule, standings and live timing: OK",
            };
        }
        Refresh();

        var refresh = new Button { Content = "Refresh" };
        refresh.Click += (_, _) => Refresh();

        // Desktop widgets (APEX.exe -Desktop): pick one, add it; drag to move, right-click to resize or remove.
        (string Id, string Name)[] kinds = [("race", "APEX · Race Mode"), ("next", "Next session"), ("countdown", "Countdown"),
            ("timing", "Live timing"), ("driver", "Driver"), ("fav", "Favourite driver"), ("wdc", "Drivers' championship"),
            ("wcc", "Constructors' championship"), ("weekend", "Race weekend")];
        var widget = new ComboBox { Header = "Widget", MinWidth = 320 };
        foreach (var k in kinds) widget.Items.Add(k.Name);
        widget.SelectedIndex = 0;
        var size = new RadioButtons { Header = "Size", MaxColumns = 3 };
        foreach (var s in new[] { "Small", "Medium", "Large" }) size.Items.Add(s);
        size.SelectedIndex = 1;
        var add = new Button { Content = "Add to desktop" };
        add.Click += (_, _) =>
        {
            DesktopConfig.Add(kinds[widget.SelectedIndex].Id, "sml"[size.SelectedIndex].ToString());
            DesktopConfig.EnsureHostRunning();
        };
        var lockScreen = new HyperlinkButton { Content = "Open lock screen settings", Padding = new Thickness(0) };
        lockScreen.Click += async (_, _) => await Windows.System.Launcher.LaunchUriAsync(new Uri("ms-settings:lockscreen"));
        TextBlock H(string t) => new() { Text = t, FontSize = 18, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold };
        TextBlock P(string t) => new() { Text = t, TextWrapping = TextWrapping.Wrap, Opacity = 0.75 };

        return new ScrollViewer
        {
            Content = new StackPanel
            {
                Spacing = 24,
                Padding = new Thickness(32, 48, 32, 32),
                Children =
                {
                    new TextBlock { Text = "APEX", FontSize = 28, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold },
                    driver,
                    density,
                    H("On your desktop"),
                    P("Drag a widget to move it. Right-click it to change its size or remove it."),
                    widget,
                    size,
                    add,
                    H("Widgets board and lock screen"),
                    P("Press Win + W, then Add widgets, and pick APEX. For the lock screen, open lock screen settings, choose Widgets, and add an APEX widget (small widgets fit there)."),
                    lockScreen,
                    H("Data"),
                    status,
                    refresh,
                },
            },
        };
    }
}
