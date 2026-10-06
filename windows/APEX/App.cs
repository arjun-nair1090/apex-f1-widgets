using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media;

namespace Apex;

/// Companion window (spec §17). Widgets are customized natively on the board (Customize menu); this sets defaults for new
/// widgets and shows data health. Built in code (no XAML pages) and themed by the system, so it feels native.
public sealed class App : Application
{
    Window? window;

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
        var driver = new ComboBox { Header = "Driver for new widgets", PlaceholderText = "Loading drivers…", MinWidth = 320 };
        var density = new RadioButtons { Header = "Information", MaxColumns = 3 };
        foreach (var d in new[] { "Minimal", "Standard", "Detailed" }) density.Items.Add(d);
        density.SelectedIndex = defaults.Density switch { "minimal" => 0, "detailed" => 2, _ => 1 };

        List<DriverSummary> drivers = [];
        void Save() => Defaults.Save(new WidgetSettings(
            driver.SelectedIndex > 0 ? drivers[driver.SelectedIndex - 1].Id : null,
            ((string)density.SelectedItem).ToLowerInvariant()));
        driver.SelectionChanged += (_, _) => Save();
        density.SelectionChanged += (_, _) => Save();

        async void Refresh()
        {
            drivers = await Api.Drivers();
            driver.Items.Clear();
            driver.Items.Add("None");
            foreach (var d in drivers) driver.Items.Add($"{d.FirstName} {d.LastName}");
            driver.SelectedIndex = Math.Max(0, drivers.FindIndex(d => d.Id == defaults.Driver) + 1);
            var snap = await Api.Snapshot(defaults.Driver);
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

        return new ScrollViewer
        {
            Content = new StackPanel
            {
                Spacing = 24,
                Padding = new Thickness(32, 48, 32, 32),
                Children =
                {
                    new TextBlock { Text = "APEX", FontSize = 28, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold },
                    new TextBlock { Text = "Add APEX widgets from the Widgets board: press Win + W, then Add widgets. Use a widget's menu → Customize to change it.", TextWrapping = TextWrapping.Wrap, Opacity = 0.8 },
                    driver,
                    density,
                    new TextBlock { Text = "Data", FontWeight = Microsoft.UI.Text.FontWeights.SemiBold },
                    status,
                    refresh,
                },
            },
        };
    }
}
