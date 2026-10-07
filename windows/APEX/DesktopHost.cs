using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.XamlTypeInfo;
using WinRT.Interop;

namespace Apex;

/// One widget on the desktop. X/Y are physical pixels; -1 = not placed yet.
public record DesktopWidget(string Id, string Kind, string Size, int X = -1, int Y = -1);

/// %LOCALAPPDATA%\APEX\desktop.json: shared by the companion window (adds) and the desktop host (shows, moves, removes).
public static class DesktopConfig
{
    public static readonly string Dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "APEX");
    static readonly string FilePath = Path.Combine(Dir, "desktop.json");

    public static List<DesktopWidget>? Load()
    {
        try { return JsonSerializer.Deserialize<List<DesktopWidget>>(File.ReadAllText(FilePath)); }
        catch (FileNotFoundException) { return null; }
        catch { return []; }  // unreadable mid-write: treat as empty for this pass; the watcher fires again
    }

    public static void Save(IEnumerable<DesktopWidget> items)
    {
        Directory.CreateDirectory(Dir);
        var tmp = FilePath + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(items.ToList()));
        File.Move(tmp, FilePath, overwrite: true);
    }

    public static void Add(string kind, string size) =>
        Save([.. Load() ?? [], new DesktopWidget(Guid.NewGuid().ToString("N")[..8], kind, size)]);

    /// Starts the desktop host if it isn't running (it is single-instance and watches desktop.json).
    public static void EnsureHostRunning() => Process.Start(Environment.ProcessPath!, "-Desktop");
}

/// APEX.exe -Desktop: hosts the desktop widgets. One frameless WebView2 window per widget, kept on the desktop layer.
public sealed class DesktopApp : Application, IXamlMetadataProvider
{
    readonly XamlControlsXamlMetaDataProvider controlsMetadata = new();
    public IXamlType GetXamlType(Type type) => controlsMetadata.GetXamlType(type);
    public IXamlType GetXamlType(string fullName) => controlsMetadata.GetXamlType(fullName);
    public XmlnsDefinition[] GetXmlnsDefinitions() => controlsMetadata.GetXmlnsDefinitions();

    readonly Dictionary<string, WidgetWindow> windows = [];
    DispatcherQueue? ui;
    FileSystemWatcher? watcher;

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        Resources.MergedDictionaries.Add(new XamlControlsResources());
        DispatcherShutdownMode = DispatcherShutdownMode.OnExplicitShutdown;  // keep running with zero widgets
        ui = DispatcherQueue.GetForCurrentThread();
        // First run: start with Race Mode and the favourite driver, so the desktop isn't empty.
        if (DesktopConfig.Load() is null)
            DesktopConfig.Save([new("race", "race", "m"), new("fav", "fav", "m")]);
        Sync();
        // desktop.json: widgets added/moved/removed. defaults.json: favourite driver or density changed in the app.
        watcher = new FileSystemWatcher(DesktopConfig.Dir, "*.json") { EnableRaisingEvents = true };
        FileSystemEventHandler changed = (_, e) => ui.TryEnqueue(() =>
        {
            if (e.Name == "desktop.json") Sync();
            else if (e.Name == "defaults.json") foreach (var w in windows.Values) w.Navigate();
        });
        watcher.Changed += changed;
        watcher.Created += changed;
        watcher.Renamed += (s, e) => changed(s, e);
    }

    /// Make the open windows match desktop.json (adds from the companion, size changes, removals).
    void Sync()
    {
        var items = DesktopConfig.Load() ?? [];
        foreach (var id in windows.Keys.Except(items.Select(i => i.Id)).ToList())
        {
            windows[id].Close();
            windows.Remove(id);
        }
        int stack = 0;
        foreach (var item in items)
        {
            if (windows.TryGetValue(item.Id, out var w))
            {
                if (w.Item.Size != item.Size || w.Item.Kind != item.Kind) w.Apply(item);
            }
            else
            {
                windows[item.Id] = new WidgetWindow(item, stack++, OnCommand);
            }
        }
    }

    void OnCommand(WidgetWindow w, string cmd)
    {
        var items = DesktopConfig.Load() ?? [];
        var i = items.FindIndex(x => x.Id == w.Item.Id);
        if (i < 0) return;
        switch (cmd)
        {
            case "remove": items.RemoveAt(i); break;
            case "settings": Process.Start(Environment.ProcessPath!); return;
            default: items[i] = w.Item; break;  // moved or resized: persist
        }
        DesktopConfig.Save(items);
    }
}

sealed class WidgetWindow : Window
{
    static readonly Dictionary<string, (int W, int H)> Sizes = new() { ["s"] = (170, 170), ["m"] = (364, 170), ["l"] = (364, 382) };
    public DesktopWidget Item { get; private set; }
    readonly WebView2 web = new();
    readonly IntPtr hwnd;
    readonly Action<WidgetWindow, string> onCommand;

    public WidgetWindow(DesktopWidget item, int stack, Action<WidgetWindow, string> onCommand)
    {
        Item = item;
        this.onCommand = onCommand;
        Title = "APEX widget";
        // Carbon behind the page so no default-white window background shows at the edges or while loading.
        var carbon = Windows.UI.Color.FromArgb(255, 0x15, 0x15, 0x1E);
        web.DefaultBackgroundColor = carbon;
        Content = new Grid { Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(carbon), Children = { web } };
        hwnd = WindowNative.GetWindowHandle(this);

        var frame = OverlappedPresenter.Create();
        frame.SetBorderAndTitleBar(false, false);
        frame.IsResizable = frame.IsMaximizable = frame.IsMinimizable = false;
        AppWindow.SetPresenter(frame);
        AppWindow.IsShownInSwitchers = false;  // not in the taskbar or Alt+Tab: it lives on the desktop
        int round = 2, noBorder = unchecked((int)0xFFFFFFFE);  // DWMWCP_ROUND corners; DWMWA_COLOR_NONE: no 1px frame
        DwmSetWindowAttribute(hwnd, 33, ref round, sizeof(int));
        DwmSetWindowAttribute(hwnd, 34, ref noBorder, sizeof(int));

        Place(stack);
        Activated += (_, _) => SendToBottom();  // a click raises a window; put it back on the desktop layer
        // The presenter keeps a 3px dialog frame and re-applies it whenever styles change. Answer WM_NCCALCSIZE
        // with "no frame" instead, so the page fills the whole window whatever the styles say.
        frameless = (h, msg, w, l, _, _) => msg == 0x0083 /* WM_NCCALCSIZE */ && w != 0 ? 0 : DefSubclassProc(h, msg, w, l);
        SetWindowSubclass(hwnd, frameless, 1, 0);
        AppWindow.Show(false);
        SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020 /* NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED */);
        SendToBottom();
        _ = InitAsync();
    }

    double Scale => GetDpiForWindow(hwnd) / 96.0;

    void Place(int stack)
    {
        var (w, h) = Sizes[Item.Size];
        int pw = (int)(w * Scale), ph = (int)(h * Scale);
        int x = Item.X, y = Item.Y;
        if (x < 0 || y < 0)  // unplaced: stack down the right edge of the primary work area
        {
            var area = DisplayArea.Primary.WorkArea;
            x = area.X + area.Width - pw - (int)(24 * Scale);
            y = area.Y + (int)(24 * Scale) + stack * (int)((170 + 16) * Scale);
        }
        AppWindow.MoveAndResize(new Windows.Graphics.RectInt32(x, y, pw, ph));
    }

    public void Apply(DesktopWidget item)
    {
        Item = item with { X = AppWindow.Position.X, Y = AppWindow.Position.Y };
        Place(0);
        Navigate();
    }

    async Task InitAsync()
    {
        await web.EnsureCoreWebView2Async();
        var s = web.CoreWebView2.Settings;
        s.AreDefaultContextMenusEnabled = false;
        s.AreDevToolsEnabled = false;
        s.IsZoomControlEnabled = false;
        s.IsStatusBarEnabled = false;
        web.CoreWebView2.WebMessageReceived += (_, e) => OnMessage(e.TryGetWebMessageAsString());
        // The data server may still be starting (logon): retry until the page loads.
        web.CoreWebView2.NavigationCompleted += async (_, e) =>
        {
            if (e.IsSuccess) return;
            await Task.Delay(5000);
            Navigate();
        };
        Navigate();
    }

    public void Navigate()
    {
        var d = Defaults.Load();
        web.Source = new Uri($"{Api.BaseUrl}/desktop.html?w={Item.Kind}&s={Item.Size}&density={d.Density}" +
                             (d.Driver is null ? "" : $"&driver={Uri.EscapeDataString(d.Driver)}"));
    }

    void OnMessage(string message)
    {
        switch (message)
        {
            case "drag":
                ReleaseCapture();
                SendMessage(hwnd, 0xA1 /* WM_NCLBUTTONDOWN */, 2 /* HTCAPTION */, 0);  // native move until mouse-up
                Item = Item with { X = AppWindow.Position.X, Y = AppWindow.Position.Y };
                SendToBottom();
                onCommand(this, "moved");
                break;
            case "size:s" or "size:m" or "size:l":
                Apply(Item with { Size = message[5..] });
                onCommand(this, "resized");
                break;
            case "remove" or "settings":
                onCommand(this, message);
                break;
        }
    }

    void SendToBottom() => SetWindowPos(hwnd, 1 /* HWND_BOTTOM */, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 /* NOSIZE|NOMOVE|NOACTIVATE */);

    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
    [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr hwnd);
    delegate nint SubclassProc(IntPtr hwnd, uint msg, nint wParam, nint lParam, nint id, nint data);
    SubclassProc? frameless;  // field: the native side holds only a pointer, so keep the delegate alive
    [DllImport("comctl32.dll")] static extern bool SetWindowSubclass(IntPtr hwnd, SubclassProc proc, nint id, nint data);
    [DllImport("comctl32.dll")] static extern nint DefSubclassProc(IntPtr hwnd, uint msg, nint wParam, nint lParam);
    [DllImport("user32.dll")] static extern bool ReleaseCapture();
    [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
}
